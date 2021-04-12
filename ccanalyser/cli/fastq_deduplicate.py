#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct  4 13:47:20 2019
@author: asmith
"""
import os
from collections import Counter
from multiprocessing import SimpleQueue
from typing import List, Tuple, Union

import click
import numpy as np
import ujson
from ccanalyser.tools.deduplicate import (ReadDeduplicationParserProcess,
                                          ReadDuplicateRemovalProcess)
from ccanalyser.tools.io import FastqReaderProcess, FastqWriterProcess
from ccanalyser.tools.statistics import DeduplicationStatistics
from ccanalyser.utils import invert_dict, load_json
from xopen import xopen

def parse(input_files: Tuple, output: os.PathLike = "out.json", read_buffer: int = 1e5):
    """
    Parses fastq file(s) into easy to deduplicate format.

    This command parses one or more fastq files and generates a dictionary containing
    hashed read identifiers together with hashed concatenated sequences. The hash dictionary
    is output in json format and the identify subcommand can be used to determine which read identifiers 
    have duplicate sequences. 
    
    \f
    Args:
     input_files (Tuple): One or more fastq files to process
     output (os.PathLike, optional): Output for parsed read identifiers and sequences. Defaults to "out.json".
     read_buffer (int, optional): Number of reads to process before outputting to file. Defaults to 1e5.
    """    


    # Set up multiprocessing variables
    inputq = SimpleQueue()  # Reads are placed into this queue for deduplication
    writeq = SimpleQueue()  # Deduplicated reads are placed into the queue for writing

    reader = FastqReaderProcess(
        input_files=input_files,
        outq=inputq,
        n_subprocesses=1,
        read_buffer=read_buffer,
    )

    parser = ReadDeduplicationParserProcess(
        inq=inputq, outq=writeq, save_hashed_dict_path=output
    )

    processes = [reader, parser]

    for proc in processes:
        proc.start()

    for proc in processes:
        proc.join()
        proc.terminate()


def identify(input_files: Tuple, output: os.PathLike = "duplicates.json"):
    """
    Identifies fragments with duplicated sequences.

    Merges the hashed dictionaries (in json format) generated by the "parse" subcommand and 
    identifies read with exactly the same sequence (share an identical hash). Duplicated read
    identifiers (hashed) are output in json format. The "remove" subcommand uses this dictionary
    to remove duplicates from fastq files.
    

    \f
    Args:
     input_files (Tuple): Paths to json files containing dictionaries with hashed read ids as the keys
                          and hashed sequences as the values.
     output (os.PathLike, optional): Duplicate read ids identified. Defaults to "duplicates.json".
    """    


    dedup_sequences = dict()
    read_ids = set()

    np.random.shuffle(np.array(input_files))
    for fn in input_files:
        d = load_json(fn)  # {READ_NAME_HASH: SEQUENCE_HASH}
        read_ids.update(d)
        dedup_sequences.update(invert_dict(d))  # {SEQUENCE_HASH: READ_NAME_HASH}

    duplicated_ids = read_ids - set(dedup_sequences.values())
    del read_ids
    del dedup_sequences

    with xopen(output, "w") as w:
        duplicated_ids_dict = dict.fromkeys(duplicated_ids)
        ujson.dump(duplicated_ids_dict, w)


def remove(
    input_files: Tuple,
    duplicated_ids: os.PathLike,
    read_buffer: int = 1e5,
    output_prefix: os.PathLike = "",
    gzip: bool = False, 
    compression_level: int = 5,
    sample_name: str = "",
    stats_prefix: os.PathLike="",
):
    """
    Removes fragments with duplicated sequences from fastq files.
    
    Parses input fastq files and removes any duplicates from the fastq file(s) that are
    present in the json file supplied. This json dictionary should be produced by the 
    "identify" subcommand. 

    Statistics for the number of duplicated and unique reads are also provided.

    \f
    Args:
     input_files (Tuple): Input fastq files (in the same order as used for the parse command).
     duplicated_ids (os.PathLike): Duplicated read ids from identify command (hashed and in json format).
     read_buffer (int, optional): Number of reads to process before writing to file. Defaults to 1e5.
     output_prefix (os.PathLike, optional): Deduplicated fastq output prefix. Defaults to "".
     gzip (bool, optional): Determines if output is gzip compressed using pigz. Defaults to False.
     compression_level (int, optional): Level of compression if required (1-9). Defaults to 5.
     sample_name (str, optional): Name of sample processed e.g. DOX-treated_1. Defaults to "".
     stats_prefix (os.PathLike, optional): Output prefix for statistics. Defaults to "".
    
    """

    duplicated_ids = set(load_json(duplicated_ids))
    inputq = SimpleQueue()  # Reads are placed into this queue for deduplication
    writeq = SimpleQueue()  # Deduplicated reads are placed into the queue for writing
    statq = SimpleQueue()  # Statistics are sent on this queue for processing

    output_files = [
        f"{output_prefix}_{ii+1}.fastq{'.gz' if gzip else ''}" for ii in range(len(input_files))
    ]

    deduplicator = [
        ReadDuplicateRemovalProcess(
            inq=inputq, outq=writeq, duplicated_ids=duplicated_ids, statq=statq
        )
        for _ in range(1) # Placeholder to enable multiple digestion processes at a later date
    ]

    del duplicated_ids # Reduces memory usage before starting (likely by forking) a new process

    reader = FastqReaderProcess(
        input_files=input_files,
        outq=inputq,
        read_buffer=read_buffer,
        n_subprocesses=1,
    )

    writer = FastqWriterProcess(
        inq=writeq,
        output=output_files,
        compression_level=compression_level,
    )

    reader.start()
    writer.start()
    for dedup in deduplicator:
        dedup.start()

    processes = [writer, reader, *deduplicator]

    for proc in processes:
        proc.join()
        proc.terminate()

    # Handle statistics
    stats_aggregator = Counter()
    stats = statq.get()

    while not stats == "END":
        stats_aggregator.update(stats)
        stats = statq.get()

    deduplication_stats = DeduplicationStatistics(
        sample=sample_name, **stats_aggregator
    )

    deduplication_stats.df.to_csv(f"{stats_prefix}.deduplication.csv", index=False)
