import os
import pandas as pd
from ekorpkit import eKonf
from ekorpkit.io.file import save_dataframe


class HFDS:
    def __init__(self, **args):
        self.args = eKonf.to_config(args)
        self.autoload = self.args.get("autoload", True)
        self.name = self.args.get("name", None)
        self.subsets = self.args.get("subsets", None)
        self.splits = self.args.get("splits", None)
        self.verbose = self.args.get("verbose", True)

        self.output_dir = self.args.output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.output_file = os.path.join(self.output_dir, self.args.output_file)
        self.force_download = self.args.force_download

        if self.autoload:
            self.build()

    def build(self):
        if not os.path.exists(self.output_file) or self.force_download:
            self.build_hfds()
        else:
            print(f"{self.output_file} already exists. skipping..")

    def build_hfds(self):
        from datasets import load_dataset

        dataset_name = self.name
        subsets = self.subsets
        splits = self.splits
        if isinstance(subsets, str):
            subsets = [subsets]
        elif not isinstance(subsets, list):
            subsets = [None]
        if isinstance(splits, str):
            splits = [splits]
        elif not isinstance(splits, list):
            subsets = [None]

        dfs = []
        for subset in subsets:
            for split in splits:
                ds = load_dataset(dataset_name, subset, split=split)
                print(ds)
                df = ds.to_pandas()
                df["subset"] = subset
                df["split"] = split
                dfs.append(df)

        df = pd.concat(dfs, ignore_index=True)
        save_dataframe(df, self.output_file)
        if self.verbose:
            print(df.tail())
        print(f"Saved {len(df.index)} documents to {self.output_file}")
