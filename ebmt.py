#!/bin/env python3
#Author: Saurabh Pathak
'''this module performs the first stage of the translation system
partially adapted from description in 2010 paper by Peter Koehn et al.'''
from editdist import edit_dist
import pickle, math, collections, sys, data

line, l = [], 0

class ExactMatchException(Exception):

    def __init__(self, trans):
        super(ExactMatchException, self).__init__(self)
        self.info = trans

class _BestMatch:
    '''Handler class for EBMT - translation unit is a sentence.'''

    def __init__(self, dbdir, thresh=0.3, mx=5):
        self.__threshold, self.__mx = thresh, mx
        with open(dbdir+'suffixarray.data', 'rb') as sf, open(dbdir+'ebmt.data', 'rb') as sd: self.__sf, self.__sd = pickle.load(sf), pickle.load(sd)
        self.__sflen, self.__f, self.__fl = len(self.__sf), data.f.split(), data.f.splitlines()

    def match(self):
        d1, d2 = collections.defaultdict(list), collections.defaultdict(list)
        for i in range(l):
            d1[line[i]].append(i)
            if i < l-1: d2[' '.join(line[i:i+2])].append(i)
        self.__ceilingcost = math.ceil(self.__threshold * l)
        #print('ceil before:', self.__ceilingcost, file=sys.stderr)
        M = self.__find_matches()
        #print('ceil after', self.__ceilingcost, file=sys.stderr)
        S = self.__find_segments(M, d1, d2)
        #for s in S: print(s.s)
        return self.__best_match(S) if len(S) > self.__mx else self.__score(S) if len(S) != 0 else S

    def __find_segments(self, M, d1, d2):
        A, S = [], []
        for k, v in M.items():
            if len(v) == 0: continue
            a = data._Item()
            a.M, a.s = v, self.__fl[k]
            a.sumlength = sum([m.pend-m.pstart for m in v])
            a.priority = - a.sumlength
            A.append(a)

        while len(A) > 0:
            a = A.pop()
            t = a.s.split()
            u = len(t)
            if abs(u - l) > self.__ceilingcost or max(u, l) - a.sumlength > self.__ceilingcost: continue
            #print('sentence under question', a.M[0].segid, a.s, file=sys.stderr)
            #print('before', len(a.M), file=sys.stderr)
            #for m in a.M: print(' '.join(a.s.split()[m.start:m.end]), file=sys.stderr)
            for i in range(u):
                bigram = ' '.join(t[i:i+2]) if i < u-1 else None
                for start in d2.get(bigram, []):
                    end, m = start+2, data._Match()
                    m.segid, m.length, m.start, m.end = a.M[0].segid, u, i, i+2
                    m.remain = m.length - m.end
                    a.M = self.__add_match(m, a.M, start, end, l-end)
                else:
                    for start in d1.get(t[i], []):
                        end, m = start+1, data._Match()
                        m.segid, m.length, m.start, m.end = a.M[0].segid, u, i, i+1
                        m.remain = m.length - m.end
                        a.M = self.__add_match(m, a.M, start, end, l-end)
            #print('after', len(a.M), file=sys.stderr)
            a.M.sort(key=lambda x: x.start)
            #for m in a.M: print(' '.join(a.s.split()[m.start:m.end]), file=sys.stderr)
            cost = self.__parse_validate(a.M)
            #print(cost, self.__ceilingcost, file=sys.stderr)
            if cost < self.__ceilingcost: self.__ceilingcost, S = cost, [a]
            elif cost == self.__ceilingcost: S.append(a)
        return S

    def __parse_validate(self, M):
        A = []
        for m1 in M:
            for m2 in M:
                a = self.__combinable(m1, m2)
                if a is not None: A.append(a)
        cost = min([m.leftmax + m.rightmax for m in M])
        while len(A) > 0:
            a = A.pop()
            if a.mincost > self.__ceilingcost: continue
            mm = data._Match()
            mm.leftmin, mm.leftmax, mm.rightmin, mm.rightmax, mm.start, mm.end, mm.pstart, mm.pend, mm.internal = a.m1.leftmin, a.m1.leftmax, a.m2.rightmin, a.m2.rightmax, a.m1.start, a.m2.end, a.m1.pstart, a.m2.pend, a.m1.internal + a.m2.internal + a.internal
            cost = min(cost, mm.leftmax + mm.rightmax + mm.internal)
            for m in M:
                a = self.__combinable(mm, m)
                if a is not None: A.append(a)
        return cost

    def __combinable(self, m1, m2):
        if m1.end > m2.start or m1.pend > m2.pstart: return
        a = data._Item()
        a.m1, a.m2, a.internal = m1, m2, max(m2.start - m1.end - 1, m2.pstart - m1.pend - 1)
        a.mincost = a.priority = m1.leftmin + m2.rightmin + a.internal
        return a

    def __find_matches(self):
        M = collections.defaultdict(list)
        for start in range(l):
            self.__first_match = 0
            for end in range(start + 3, l+1):
                N = self.__find_in_suffix_array(' '.join(line[start:end]), end-start)
                if N is None: break
                for m in N: M[m.segid] = self.__add_match(m, M[m.segid], start, end, l-end)
        #for key in M.keys(): print(self.__fl[key])
        return M

    def __add_match(self, m, M, start, end, remain):
        k = []
        for mm in M:
            if (mm.end >= m.end and mm.start <= m.start) or (mm.pend >= end and mm.pstart <= start): return M
            elif m.start <= mm.start <= m.end and m.start <= mm.end <= m.end: continue
            k.append(mm)
        m.leftmin = abs(m.start - start)
        if m.leftmin == 0 and start > 0: m.leftmin = 1
        m.rightmin = abs(m.remain - remain)
        if m.rightmin == 0 and remain > 0: m.rightmin = 1
        m.leftmax, m.rightmax, mincost = max(m.start, start), max(m.remain, remain), m.leftmin + m.rightmin
        #I found that both the following lines have a negative impact (incorrect output in many cases). See my thesis
        #self.__ceilingcost = min(m.leftmax + m.rightmax, self.__ceilingcost)  # <-- also, this line is described in paper text but not in their pseudocode
        #if mincost > self.__ceilingcost: return M
        m.internal, m.pstart, m.pend = 0, start, end
        k.append(m)
        return k

    def __find_in_suffix_array(self, p, plen):

        def binary_search(lo, hi=self.__sflen, *, first=True):
            '''to find first/last (as requested in parameter) occurence of string in text'''
            while hi > lo:
                mid = (lo + hi) // 2
                pos = self.__sf[mid]
                k = ' '.join(self.__f[pos:pos+plen])
                if k < p: lo = mid + 1
                elif k > p: hi = mid
                elif first:
                    if mid == 0: return mid
                    prevpos = self.__sf[mid-1]
                    if ' '.join(self.__f[prevpos:prevpos+plen]) != k: return mid
                    hi = mid - 1
                else:
                    if mid == self.__sflen - 1: return mid
                    nextpos = self.__sf[mid+1]
                    if ' '.join(self.__f[nextpos:nextpos+plen]) != k: return mid
                    lo = mid + 1
            raise KeyError

        try: self.__first_match = binary_search(self.__first_match)
        except KeyError: return
        N, self.__last_match = [], binary_search(self.__first_match, first=False)
        for i in range(self.__first_match, self.__last_match + 1):
            m = data._Match()
            m.segid, m.length, m.start = self.__sd[self.__sf[i]]
            m.end = m.start + plen
            m.remain = m.length - m.end
            N.append(m)
        return N
        
    def __calc_FMS(self, x):
        x.fms = round(1  - edit_dist(x.s.split(),line) / max(l, len(x.s.split())), 4)
        return x.fms

    def __best_match(self, S): #finds exact match. Main must catch the exact match exception.
        S.sort(key=self.__calc_FMS, reverse=True)
        return self.__score(S[:self.__mx])

    def __score(self, S):
        if not hasattr(S[0], 'fms'):
            for s in S: self.__calc_FMS(s)
        if S[0].fms == 1: raise ExactMatchException(data.e[S[0].M[0].segid])
        #s = sum(x.fms for x in S)
        #for r in S: r.fms = round(r.fms/s, 4)
        return S

def align(item):

    def mismatch(sstart, sentend):
        nonlocal matched_target
        for i in range(sstart, sentend):
            for t in alignment.get(i, []): matched_target[t] = False

    def merge_chunks():

        def merge():
            nonlocal chunks, lenchunks
            i = 0
            while i < lenchunks - 1:
                j = i + 1
                while j < lenchunks:
                    c1, c2 = chunks[i], chunks[j]
                    c1len = c1.end - c1.start
                    c1ilen = c1.iend - c1.istart
                    c2len = c2.end - c2.start
                    c2ilen = c2.iend - c2.istart
                    minilen = min(c1.istart, c2.istart)
                    minlen = min(c1.start, c2.start)
                    maxlen = max(c1.end, c2.end)
                    maxilen = max(c1.iend, c2.iend)
                    interilen = maxilen - minilen
                    interlen = maxlen - minlen
                    if interilen <= c1ilen + c2ilen and interlen <= c1len + c2len:
                        c1.istart = minilen
                        c1.start = minlen
                        c1.iend = maxilen
                        c1.end = maxlen
                        chunks.remove(c2)
                        lenchunks -= 1
                    else: j += 1
                i += 1

        nonlocal chunks, lenchunks
        oldlenchunks = lenchunks+1
        while oldlenchunks > lenchunks: 
            oldlenchunks = lenchunks
            merge()

        i = 0
        while i < lenchunks - 1:
            c1, c2 = chunks[i], chunks[i+1]
            if c1.istart <= c2.istart < c1.iend and c1.istart < c2.iend <= c1.iend:
                chunks.remove(c2)
                lenchunks -= 1
            elif c2.istart <= c1.istart < c2.iend and c2.istart < c1.iend <= c1.iend:
                chunks.remove(c1)
                lenchunks -= 1
            else: i += 1

    def grow_chunk(i, j):
        nonlocal chunks, matched_target
        #if j is not None: matched_target[j] = False
        for k in range(lenchunks):
            sside = 'chunks[k].pstart -= 1; chunks[k].istart -= 1' if i == chunks[k].pstart-1 else 'chunks[k].pend += 1; chunks[k].iend += 1' if i == chunks[k].pend else None
            if sside is None: continue
            if j is None:
                exec(sside)
                return True
            tside = 'chunks[k].start -= 1' if j == chunks[k].start-1 else 'chunks[k].end += 1' if i == chunks[k].end else None
            if tside is None: continue
            exec('{};{}'.format(sside, tside))
            return True
        return False

    #print(item.s, file=sys.stderr)
    #for m in item.M: print(' '.join(item.s.split()[m.start:m.end]), m.pstart, m.pend, m.start, m.end, file=sys.stderr)
    segid, alignment = item.M[0].segid, collections.defaultdict(list)
    for x, y in map(lambda p: tuple(map(int, p.split('-'))), data.al[segid].split()): alignment[x].append(y)
    istart = sstart = 0
    slen, d = len(item.s), None
    matched_target = [True] * len(data.e[segid].split())
    #print(alignment, file=sys.stderr)
    for i in range(len(item.M)):
        m = item.M[i]
        if m.pstart < istart:
            d = i
            continue
        mismatch(sstart, m.start)
        istart, sstart = m.pend, m.end
    if sstart < slen: mismatch(sstart, slen)
    if d is not None: del item.M[d]
    #print(matched_target, file=sys.stderr)
    #print(target, file=sys.stderr)
    chunks, lenchunks = [], 0
    for m in item.M:
        for i, k in zip(range(m.start, m.end), range(m.pstart, m.pend)):
            al = alignment.get(i)
            if al is not None:
                same = False
                for j in al:
                    if matched_target[j]:# and not grow_chunk(i, j) and not same:
                        chunk = data._Match()
                        chunk.segid, chunk.fms, chunk.pstart, chunk.pend, chunk.start, chunk.end, chunk.istart, chunk.iend = segid, item.fms, i, i+1, j, j+1, k, k+1
                        chunks.append(chunk)
                        lenchunks += 1
                    same = True
            #else: grow_chunk(i, None)
    merge_chunks()
    #for m in chunks: print(' '.join(target[m.start:m.end]), ' '.join(item.s[m.pstart:m.pend]), m.istart, m.iend, m.pstart, m.pend, m.start, m.end, file=sys.stderr)
    return chunks

def construct_chunkset(S):
    chunkset = []
    for s in S: chunkset.extend(align(s))
    return chunkset

def run(text, bm, length):
    global line, l
    line, l = text, length
    return construct_chunkset(bm.match())

if __name__=="__main__":
    import xml_input
    with open(sys.argv[1]) as ip:
        print('Loading EBMT...', sep='', end='', flush=True, file=sys.stderr)
        data.load()
        bm = _BestMatch(data.dbdir, float(sys.argv[2]), int(sys.argv[3]))
        print('Done', file=sys.stderr)
        for text in ip:
            text = text.split()
            length = len(text)
            chunkset = run(text, bm, length)
            if len(chunkset) != 0: print(xml_input.construct(chunkset, text, length))
            else : print(line)
