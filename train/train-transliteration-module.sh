#!/bin/bash
#Author: Saurabh Pathak
#Credits: Adapted from moses transliteration training script of the same name.
#This adaptation is specific to my use and is not general purpose like the script. However, unlike it, this script can train with both hierarchical and phrase-based models.
function usage {
	echo "usage: train-transliteration-module.sh corpus_stem alignmentfile outputdir hpb|pb"
	exit 1
}

if [ $# -ne 4 ]
then usage
fi

change_absolute () {
	if [ "${1:0:1}" = "/" ]
	then echo $1
	else echo "$PWD/$1"
	fi
}

function main {
	export PYTHONIOENCODING=utf-8
	if [ "$4" = "hpb" ]
	then
		echo Will train hierarchical model...
		h="-hierarchical -glue-grammar"
		H="-Hierarchical"
		B="CreateOnDiskPt 1 1 4 100 2"
		D="-threads $cores -drop-unknown -v 0"
	elif [ "$4" = "pb" ]
	then
		echo Will train phrase based model...
		h=""
		H=""
		B="processPhraseTableMin"
		D="-threads $cores -drop-unknown -v 0 -distortion-limit 0"
	else echo Wrong model requested: $4 && exit 1
	fi
	OUT_DIR=$(change_absolute $3)
	IN_DIR=$(change_absolute $1)
	mkdir -p $OUT_DIR
	ln -s $IN_DIR.hi $OUT_DIR/f
	ln -s $IN_DIR.en $OUT_DIR/e
	ln -s $(change_absolute $2) $OUT_DIR/a
	mine_transliterations
	train_transliteration_module
	retrain_transliteration_module
	rm -rf model # <-- stray empty dir created by train-model.perl
	echo "Training Transliteration Module - End ". $(date)
}

function learn_transliteration_model {
	cp $OUT_DIR/training/corpus$1.en $OUT_DIR/lm/target
	echo Align Corpus
	$SCRIPTS_ROOTDIR/training/train-model.perl -mgiza -mgiza-cpus $cores -dont-zip -last-step 3 -external-bin-dir /opt/mgiza/bin -f hi -e en -alignment grow-diag-final-and -score-options '--KneserNey' -corpus $OUT_DIR/training/corpus$t -corpus-dir $OUT_DIR/training/prepared -giza-e2f $OUT_DIR/training/giza -giza-f2e $OUT_DIR/training/giza-inverse -alignment-file $OUT_DIR/model/aligned -alignment-stem $OUT_DIR/model/aligned -cores $cores -parallel -sort-buffer-size $sbuffsize -sort-batch-size $sbsize -sort-parallel $cores
	echo Train Translation Models
	$SCRIPTS_ROOTDIR/training/train-model.perl -dont-zip -first-step 4 -last-step 6 -external-bin-dir /opt/mgiza/bin -f hi -e en -alignment grow-diag-final-and -score-options '--KneserNey' -lexical-file $OUT_DIR/model/lex -alignment-file $OUT_DIR/model/aligned -alignment-stem $OUT_DIR/model/aligned -corpus $OUT_DIR/training/corpus$t -model-dir $OUT_DIR/model -cores $cores -sort-buffer-size $sbuffsize -sort-batch-size $sbsize -sort-parallel $cores $h
	echo Train Language Models
	lmplz -o 5 --interpolate_unigrams 0 --discount_fallback --text $OUT_DIR/lm/target --arpa $OUT_DIR/lm/targetLM
	build_binary $OUT_DIR/lm/targetLM $OUT_DIR/lm/targetLM.bin
	echo Create Config File
	$SCRIPTS_ROOTDIR/training/train-model.perl -first-step 9 -f hi -e en -config $OUT_DIR/model/moses.ini -model-dir $OUT_DIR/model -lm 0:5:$OUT_DIR/lm/targetLM.bin:8 -external-bin-dir /opt/mgiza/bin $h
}

function mine_transliterations {
	echo "Creating Model"
	echo "Extracting 1-1 Alignments"
	1-1-Extraction $OUT_DIR/f $OUT_DIR/e $OUT_DIR/a > $OUT_DIR/1-1.hi-en
	echo "Cleaning the list for Miner"
	$SCRIPTS_ROOTDIR/Transliteration/clean.pl $OUT_DIR/1-1.hi-en > $OUT_DIR/1-1.hi-en.cleaned
	test -s $OUT_DIR/1-1.hi-en.pair-probs && echo 1-1.hi-en.pair-probs in place, reusing || (echo Extracting Transliteration Pairs && TMining $OUT_DIR/1-1.hi-en.cleaned > $OUT_DIR/1-1.hi-en.pair-probs)
	echo Selecting Transliteration Pairs with threshold 0.5
	echo 0.5 | $SCRIPTS_ROOTDIR/Transliteration/threshold.pl $OUT_DIR/1-1.hi-en.pair-probs > $OUT_DIR/1-1.hi-en.mined-pairs
}

function train_transliteration_module {
	mkdir -p $OUT_DIR/model $OUT_DIR/lm
	echo Preparing Corpus
	$SCRIPTS_ROOTDIR/Transliteration/corpusCreator.pl $OUT_DIR 1-1.hi-en.mined-pairs hi en
	test -e $OUT_DIR/training/corpusA.en && learn_transliteration_model A || learn_transliteration_model
	echo Running Tuning for Transliteration Module
	touch $OUT_DIR/tuning/moses.table.ini
	$SCRIPTS_ROOTDIR/training/train-model.perl  -mgiza -mgiza-cpus $cores -dont-zip -first-step 9 -external-bin-dir /opt/mgiza/bin -f hi -e en -alignment grow-diag-final-and -score-options '--KneserNey' -config $OUT_DIR/tuning/moses.table.ini -lm 0:5:$OUT_DIR/tuning/moses.table.ini:8 $h -model-dir $OUT_DIR/model
	$SCRIPTS_ROOTDIR/training/filter-model-given-input.pl $OUT_DIR/tuning/filtered $OUT_DIR/tuning/moses.table.ini $OUT_DIR/tuning/input -Binarizer "$B" $H
	rm $OUT_DIR/tuning/moses.table.ini
	$SCRIPTS_ROOTDIR/ems/support/substitute-filtered-tables.perl $OUT_DIR/tuning/filtered/moses.ini < $OUT_DIR/model/moses.ini > $OUT_DIR/tuning/moses.filtered.ini
	$SCRIPTS_ROOTDIR/training/mert-moses.pl $OUT_DIR/tuning/input $OUT_DIR/tuning/reference /opt/moses/bin/moses $OUT_DIR/tuning/moses.filtered.ini --nbest 100 --working-dir $OUT_DIR/tuning/tmp --rootdir /opt/moses/bin --decoder-flags "$D" -mertdir /opt/moses/bin -threads=$cores --no-filter-phrase-table
	cp $OUT_DIR/tuning/tmp/moses.ini $OUT_DIR/tuning/moses.ini
	$SCRIPTS_ROOTDIR/ems/support/substitute-weights.perl $OUT_DIR/model/moses.ini $OUT_DIR/tuning/moses.ini $OUT_DIR/tuning/moses.tuned.ini
}

function retrain_transliteration_module {
	if [ -s $OUT_DIR/training/corpusA.en ]
	then
		cd $OUT_DIR
		rm -rf model/* lm/* training/giza training/giza-inverse training/prepared
		cd - > /dev/null
		learn_transliteration_model
	fi
}

cores=16
sbsize=512
sbuffsize=10G
main $1 $2 $3 $4
exit 0
