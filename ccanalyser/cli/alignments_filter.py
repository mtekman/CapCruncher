import os
import click
import pandas as pd


from ccanalyser.cli.cli_alignments import cli
from ccanalyser.tools.io import parse_bam
from ccanalyser.tools.filter import CCSliceFilter, TriCSliceFilter, TiledCSliceFilter
from ccanalyser.utils import get_timing

SLICE_FILTERS = {
    "capture": CCSliceFilter,
    "tri": TriCSliceFilter,
    "tiled": TiledCSliceFilter,
}


@get_timing(task_name="merging annotations with BAM input")
def merge_annotations(df: pd.DataFrame, annotations: os.PathLike) -> pd.DataFrame:
    """Combines annotations with the parsed bam file output.

    Uses pandas outer join on the indexes to merge annotations
    e.g. number of capture probe overlaps.

    Annotation tsv must have the index as the first column and this index
    must have intersecting keys with the first dataframe's index.


    Args:
     df (pd.DataFrame): Dataframe to merge with annotations
     annotations (os.PathLike): Filename of .tsv to read and merge with df

    Returns:
     pd.DataFrame: Merged dataframe
    """

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
    help="Annotations for the bam file that must contain the required columns, see description.",
    required=True,
)
@click.option(
    "--custom_filtering",
    help="Custom filtering to be used. This must be supplied as a path to a yaml file.",
    default=None,
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
    "--gzip/--no-gzip", help="Determines if files are gziped or not", default=False
)
def filter(
    bam: os.PathLike,
    annotations: os.PathLike,
    custom_filtering: os.PathLike = None,
    output_prefix: os.PathLike = "reporters",
    stats_prefix: os.PathLike = "",
    method: str = "capture",
    sample_name: str = "",
    read_type: str = "",
    gzip: bool = False,
):
    """
    Removes unwanted aligned slices and identifies reporters.

    Parses a BAM file and merges this with a supplied annotation to identify unwanted slices.
    Filtering can be tuned for Capture-C, Tri-C and Tiled-C data to ensure optimal filtering.

    Common filters include:

    - Removal of unmapped slices
    - Removal of excluded/blacklisted slices
    - Removal of non-capture fragments
    - Removal of multi-capture fragments
    - Removal of non-reporter fragments
    - Removal of fragments with duplicated coordinates.

    For specific filtering for each of the three methods see:

    - :class:`CCSliceFilter <ccanalyser.tools.filter.CCSliceFilter>`
    - :class:`TriCSliceFilter <ccanalyser.tools.filter.TriCSliceFilter>`
    - :class:`TiledCSliceFilter <ccanalyser.tools.filter.TiledCSliceFilter>`


    In addition to outputting valid reporter fragments and slices separated by capture probe,
    this script also provides statistics on the number of read/slices filtered at each stage,
    and the number of cis/trans reporters for each probe.

    Notes:

     Whilst the script is capable of processing any annotations in tsv format, provided
     that the correct columns are present. It is highly recomended that the "annotate"
     subcomand is used to generate this file.

     Slice filtering is currently hard coded into each filtering class. This will be
     modified in a future update to enable custom filtering orders.


    \f
    Args:
     bam (os.PathLike): Input bam file to analyse
     annotations (os.PathLike): Annotations file generated by slices-annotate
     custom_filtering (os.PathLike): Allows for custom filtering to be performed. A yaml file is used to supply this ordering.
     output_prefix (os.PathLike, optional): Output file prefix. Defaults to "reporters".
     stats_prefix (os.PathLike, optional): Output stats prefix. Defaults to "".
     method (str, optional): Analysis method. Choose from (capture|tri|tiled). Defaults to "capture".
     sample_name (str, optional): Sample being processed e.g. DOX-treated_1. Defaults to "".
     read_type (str, optional): Process combined(flashed) or non-combined reads (pe) used for statistics. Defaults to "".
     gzip (bool, optional): Compress output with gzip. Defaults to False.
    """

    # Read bam file and merege annotations
    df_alignment = parse_bam(bam)
    df_alignment = merge_annotations(df_alignment, annotations)

    # Initialise SliceFilter
    # If no custom filtering, will use the class default.

    print(f"Filtering slices with method: {method}")
    slice_filter_type = SLICE_FILTERS[method]
    slice_filter = slice_filter_type(
        slices=df_alignment,
        sample_name=sample_name,
        read_type=read_type,
        filter_stages=custom_filtering,
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
