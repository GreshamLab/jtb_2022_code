import gc
import argparse

import anndata as ad
import numpy as np
import scanpy as sc

from jtb_2023_code.utils.figure_filenames import parse_file_path_command_line


def main():
    parse_file_path_command_line()

    ap = argparse.ArgumentParser(
        description="Package expression, velocity, and decay data"
    )

    ap.add_argument(
        "--output_file",
        "-O",
        dest="out",
        help="Output H5AD file",
        metavar="FILE",
        required=True,
    )

    args, _ = ap.parse_known_args()

    package_data(args.out)


def package_data(out_file):
    from jtb_2023_code.utils.figure_data import FigureSingleCellData

    data = FigureSingleCellData()

    _data_packager(data, out_file)


def _data_packager(data, out_file=None):

    print("Creating new data object from counts")
    _all = data.all_data

    inf_data = ad.AnnData(
        _all.layers["counts"].copy(),
        obs=_all.obs,
        var=_all.var[["CommonName", "category", "programs"]],
        dtype=_all.layers["counts"].dtype,
    )

    inf_data.layers["decay_constants"] = _all.layers["decay_constants"]

    inf_data.obs[["UMAP_1", "UMAP_2"]] = _all.obsm["X_umap"][:, 0:2]
    inf_data.obs[["PCA_1", "PCA_2"]] = _all.obsm["X_pca"][:, 0:2]

    # Copy cell cycle time to main object
    inf_data.obs["program_rapa_time"] = inf_data.obs[
        f'program_{_all.uns["programs"]["rapa_program"]}_time'
    ]
    inf_data.obs["program_cc_time"] = inf_data.obs[
        f'program_{_all.uns["programs"]["cell_cycle_program"]}_time'
    ]

    # Free memory used by all that count data and whatnot
    data._unload()

    print("Creating decay & velocity layers")

    inf_data.layers["counts"] = inf_data.X.copy()
    inf_data.X = inf_data.X.astype(np.float32)

    sc.pp.normalize_per_cell(inf_data, min_counts=0)

    # Copy decay constants and velocity from the calculated data objects
    inf_data.layers["rapamycin_velocity"] = np.full(
        inf_data.X.shape, np.nan, dtype=np.float32
    )
    inf_data.layers["cell_cycle_velocity"] = np.full(
        inf_data.X.shape, np.nan, dtype=np.float32
    )
    inf_data.layers["denoised"] = np.full(
        inf_data.X.shape,
        np.nan,
        dtype=np.float32
    )

    for k in data.expts:
        dd = data.decay_data(*k)
        _expt_idx = inf_data.obs_names.isin(dd.obs_names)

        print(f"Processing experiment {k} ({np.sum(_expt_idx)} observations)")

        inf_data.layers["denoised"][_expt_idx, :] = data.denoised_data(*k).X
        inf_data.layers["rapamycin_velocity"][_expt_idx, :] = dd.layers[
            "rapamycin_velocity"
        ]
        inf_data.layers["cell_cycle_velocity"][_expt_idx, :] = dd.layers[
            "cell_cycle_velocity"
        ]

        del dd

        print(f"Experiment extraction complete [GC: {gc.collect()}]")

    _wt_idx = inf_data.obs["Gene"] == "WT"

    print(
        f"{_wt_idx.sum()} observations kept (WT) "
        f"from {inf_data.X.shape} data"
    )

    inf_data = inf_data[_wt_idx, :].copy()

    print(
        f"Denoised NaN: {np.sum(np.isnan(inf_data.layers['denoised']))}"
    )
    print(
        "Rapamycin Velocity NaN: "
        f"{np.sum(np.isnan(inf_data.layers['rapamycin_velocity']))}"
    )
    print(
        "Velocity NaN: "
        f"{np.sum(np.isnan(inf_data.layers['cell_cycle_velocity']))}"
    )
    print(
        "Cell Cycle Decay NaN: "
        f"{np.sum(np.isnan(inf_data.layers['decay_constants']))}"
    )

    print("Calculating transcriptional output")

    inf_data.layers["rapamycin_transcription"] = inf_data.layers[
        "rapamycin_velocity"
    ].copy()
    inf_data.layers["rapamycin_transcription"] += np.multiply(
        inf_data.layers["decay_constants"], inf_data.layers["denoised"]
    )

    inf_data.layers["cell_cycle_transcription"] = inf_data.layers[
        "cell_cycle_velocity"
    ].copy()
    inf_data.layers["cell_cycle_transcription"] += np.multiply(
        inf_data.layers["decay_constants"], inf_data.layers["denoised"]
    )

    print(
        "Rapamycin Transcription NaN: "
        f"{np.sum(np.isnan(inf_data.layers['rapamycin_transcription']))}"
    )
    print(
        "Cell Cycle Transcription NaN: "
        f"{np.sum(np.isnan(inf_data.layers['cell_cycle_transcription']))}"
    )

    _has_expression = inf_data.X.sum(axis=0).A1 > 0

    if not np.all(_has_expression):
        print(f"Trimming {inf_data.shape} to {np.sum(_has_expression)} genes")
        inf_data = inf_data[:, _has_expression]

    if out_file is not None:
        print(f"Writing data {inf_data.shape} to {out_file}")
        inf_data.write(out_file)

    return inf_data


if __name__ == "__main__":
    main()
