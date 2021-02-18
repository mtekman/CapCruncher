import os
import click
import numpy as np
import pandas as pd


from ccanalyser.cli import cli
from ccanalyser.tools.io import parse_bam
from ccanalyser.tools.filter import CCSliceFilter, TriCSliceFilter, TiledCSliceFilter
from ccanalyser.utils import get_timing


@get_timing(task_name="merging annotations with BAM input")
def merge_annotations(df, annotations):
    """Combines annotations with the parsed bam file output.

    Uses pandas outer join on the indexes to merge annotations
    e.g. number of capture probe overlaps.

    Annotation tsv must have the index as the first column and this index
    must have intersecting keys with the first dataframe's index.

    Args:
     df: pd.Dataframe to merge with annotations
     annotations: Filename of .tsv to read and merge with df

    Returns:
     Merged dataframe

    """

    # Update, now using chrom and start to stop issues with multimapping
    df_ann = pd.read_csv(
        annotations,
        sep="\t",
        header=0,
        index_col=["slice_name", "chrom", "start"],
        low_memory=False,
    )
    df_ann = df_ann.drop(columns="end", errors="ignore")

    return (
        df.join(df_ann, how="inner")
        .drop(columns=["slice_name.1"], errors="ignore")
        .assign(
            restriction_fragment=lambda df: df["restriction_fragment"]
            .replace(".", 0)
            .astype(int)
        )
        .reset_index()
        .sort_values(["parent_read", "slice"])
    )


@cli.command()
@click.argument("method", type=click.Choice(["capture", "tri", "tiled"]))
@click.option("-b", "--bam", help="Bam file to process", required=True)
@click.option(
    "-a",
    "--annotations",
    help="Annotations for the bam file. Generated by slices-annotate.",
    required=True,
)
@click.option(
    "-o",
    "--output_prefix",
    help="Output prefix for deduplicated fastq file(s)",
    default="",
)
@click.option(
    "--stats_prefix",
    help="Output prefix for stats file(s)",
    default="",
)
@click.option("--sample_name", help="Name of sample e.g. DOX_treated_1")
@click.option(
    "--read_type",
    help="Type of read",
    default="flashed",
    type=click.Choice(["flashed", "pe"], case_sensitive=False),
)
@get_timing(task_name="analysis of bam file")
@click.option(
    "--gzip/--no-gzip",
    help="Determines if files are gziped or not",
    default=False
)
def reporters_identify(
    bam,
    annotations,
    output_prefix="reporters",
    stats_prefix="",
    method="capture",
    sample_name="",
    read_type="",
    gzip=False,
):

    """Removes all non-capture and non-reporter slices to identify reporters."""

    # Read bam file and merege annotations
    df_alignment = parse_bam(bam)
    df_alignment = merge_annotations(df_alignment, annotations)

    slice_filters_dict = {
        "capture": CCSliceFilter,
        "tri": TriCSliceFilter,
        "tiled": TiledCSliceFilter,
    }

    # Initialise SliceFilter with default args
    print(f"Filtering slices with method: {method}")
    slice_filter_type = slice_filters_dict[method]
    slice_filter = slice_filter_type(
        slices=df_alignment, sample_name=sample_name, read_type=read_type
    )

    # Filter slices using the slice_filter
    slice_filter.filter_slices()

    # Save filtering statisics
    slice_filter.filter_stats.to_csv(f"{stats_prefix}.slice.stats.csv", index=False)
    slice_filter.read_stats.to_csv(f"{stats_prefix}.read.stats.csv", index=False)

    # Save reporter stats
    slice_filter.cis_or_trans_stats.to_csv(
        f"{stats_prefix}.reporter.stats.csv", index=False
    )

    # Output slices filtered by capture site
    for capture_site, df_cap in slice_filter.slices.query('capture != "."').groupby(
        "capture"
    ):

        # Extract only fragments that appear in the capture dataframe
        output_slices = slice_filter.slices.loc[
            lambda df: df["parent_read"].isin(df_cap["parent_read"])
        ]
        # Generate a new slice filterer and extract the fragments
        output_fragments = slice_filter_type(output_slices).fragments

        # Output fragments and slices
        output_fragments.sort_values("parent_read").to_csv(
            f"{output_prefix}.{capture_site.strip()}.fragments.tsv{'.gz' if gzip else ''}",
            sep="\t",
            index=False,
        )

        output_slices.sort_values("slice_name").to_csv(
            f"{output_prefix}.{capture_site.strip()}.slices.tsv{'.gz' if gzip else ''}",
            sep="\t",
            index=False,
        )
