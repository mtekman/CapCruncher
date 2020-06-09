#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan  8 15:45:09 2020

@author: asmith

Script splits a fastq into specified chunks



"""
import argparse
import os
import sys
from xopen import xopen
from pysam import FastxFile


p = argparse.ArgumentParser()
p.add_argument('-i', '--input_fastq', help='BAM file to parse')
p.add_argument('--chunk_size', help='Number of reads per output file', default=1000000, type=int)
p.add_argument('-c', '--compression_level', help='Level of gzip compression (1-9 with 9 being the most compressed/slowest)',
                    default=6, type=int)
p.add_argument('-n','--output_prefix', help='output prefix')
args = p.parse_args()

def main():
    chunksize = args.chunk_size
    compression_level = args.compression_level
    prefix = args.output_prefix 
    
    split_counter = 0
    for read_counter, read in enumerate(FastxFile(args.input_fastq)):

        processed_read = f'{read}\n'.encode()

        if read_counter == 0:
            out_name = f'{prefix}_{split_counter}.fastq.gz'
            out_handle = xopen(out_name, 
                               'wb',
                               compresslevel=compression_level,
                               threads=8)
            out_handle.write(processed_read)
        
        elif read_counter % chunksize == 0:
            split_counter += 1
            out_handle.close()
            out_name = f'{prefix}_{split_counter}.fastq.gz'
            out_handle =  xopen(out_name, 
                               'wb',
                               compresslevel=compression_level,
                               threads=8)
            out_handle.write(processed_read)       
        else:
            out_handle.write(processed_read)
        
    out_handle.close()    

if __name__ == '__main__':
    main()