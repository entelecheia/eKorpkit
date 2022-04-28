from pathlib import Path
from ekorpkit import eKonf
from ekorpkit.utils.func import elapsed_timer
from ekorpkit.pipelines.pipe import apply_pipeline
from ekorpkit.io.file import load_dataframe
from hydra.utils import instantiate
from wasabi import msg


def build_corpus(**args):
    cfg = args.get("corpus", {}).get("builtin", None)
    # print(cfg)
    if cfg:
        db = DatasetBuilder(**cfg)
        db.build()


def build_t5(**args):
    cfg = args.get("dataset", {}).get("t5", None)
    # print(cfg)
    if cfg:
        db = DatasetBuilder(**cfg)
        db.build()


def build_simple(**args):
    cfg = args.get("dataset", {}).get("simple", None)
    # print(cfg)
    if cfg:
        db = DatasetBuilder(**cfg)
        db.build()


class DatasetBuilder:
    def __init__(self, **args) -> None:
        self.args = eKonf.to_dict(args)
        self.name = args.get("name", None)
        self.data_dir = args.get("data_dir", None)
        self.data_filetype = args.get("filetype", "parquet")
        self.column_info = self.args.get("column_info", None)
        self.verbose = self.args.get("verbose", False)

        self.fetch_args = args.get("fetch", None)
        self.fetch_dir = self.fetch_args.get("data_dir", None)
        self.fetch_sources = self.fetch_args.get("data_sources", None)
        if isinstance(self.fetch_sources, str):
            self.fetch_sources = [self.fetch_sources]
        if isinstance(self.fetch_sources, list):
            self.fetch_sources = {"train": self.fetch_sources}
        self.num_workers = self.fetch_args.get("num_workers", None)
        self.overwrite = self.fetch_args.get("overwrite", False)
        self.calculate_stats = self.fetch_args.get("calculate_stats", False)
        self.preprocess_text = self.fetch_args.get("preprocess_text", False)

        self.downloader = self.fetch_args.get("downloader", None)
        self.loader = self.fetch_args.get("loader", None)

        self.info_args = self.args.get("info", None)
        self.summary_info = None

        self.pipeline_args = self.args.get("pipeline", {})
        self.transform_pipeline = self.pipeline_args.get("_transform_", [])
        self.process_pipeline = self.pipeline_args.get("_preprocess_", [])
        if self.transform_pipeline is None:
            self.transform_pipeline = []
        if self.process_pipeline is None:
            self.process_pipeline = []

    def build(self):
        if self.downloader:
            if self.downloader.get("_target_", None):
                eKonf.instantiate(self.downloader)
            pipeline_args = self.downloader.get("pipeline", None)
            if pipeline_args:
                eKonf.instantiate(pipeline_args)

        if self.info_args:
            self.summary_info = eKonf.instantiate(self.info_args)
        if self.summary_info:
            self.summary_info.load(self.args)

        for split_name, split_data_source in self.fetch_sources.items():
            if split_data_source is None:
                continue
            self._process_split(split_name)

        if self.summary_info:
            self.summary_info.save()

        print(
            f"\nCorpus [{self.name}] is built to [{self.data_dir}] from [{self.fetch_dir}]"
        )

    def _process_split(self, split_name):

        output_dir = Path(self.data_dir)
        if not output_dir.is_dir():
            output_dir.mkdir(exist_ok=True, parents=True)
        output_file = output_dir / f"{self.name}-{split_name}{self.data_filetype}"
        output_meta_file = (
            output_dir / f"meta-{self.name}-{split_name}{self.data_filetype}"
        )
        sample_file_prefix = f"{str(output_dir)}/sample-{self.name}-{split_name}-"
        pipe = "save_metadata"
        if pipe in self.pipeline_args:
            if pipe not in self.transform_pipeline:
                self.transform_pipeline.append(pipe)
            self.pipeline_args[pipe]["filepath"] = str(output_meta_file)
            self.pipeline_args[pipe]["column_info"] = self.column_info
            self.pipeline_args[pipe]["split_name"] = split_name
        pipe = "save_samples"
        if pipe in self.pipeline_args:
            if pipe not in self.process_pipeline:
                self.process_pipeline.append(pipe)
            self.pipeline_args[pipe]["sample_file_prefix"] = sample_file_prefix
        pipe = "save_dataframe"
        if pipe in self.pipeline_args:
            if pipe not in self.process_pipeline:
                self.process_pipeline.append(pipe)
            self.pipeline_args[pipe]["filepath"] = str(output_file)
            columns_to_keep = self.column_info.get("data")
            if columns_to_keep:
                columns_to_keep = list(columns_to_keep.keys())
            self.pipeline_args[pipe]["columns_to_keep"] = columns_to_keep

        df = None
        if not output_file.exists() or self.overwrite:
            with elapsed_timer(format_time=True) as elapsed:
                df = instantiate(self.loader, split_name=split_name, _recursive_=False)
                msg.good(f" >> elapsed time to load and parse data: {elapsed()}")

            if df is None:
                raise ValueError("dataframe is None")

            if self.verbose:
                print(df.head())
                print(df.shape)

            if self.transform_pipeline and len(self.transform_pipeline) > 0:
                print(
                    f"\nTransforming dataframe with pipeline: {self.transform_pipeline}"
                )
                df = apply_pipeline(df, self.transform_pipeline, self.pipeline_args)

            if self.summary_info and self.calculate_stats:
                stats = {
                    "name": split_name,
                    "dataset_name": self.name,
                    "data_file": output_file.name,
                }
                if output_meta_file.is_file():
                    stats["meta_file"] = output_meta_file.name
                self.summary_info.init_stats(df=df, split_name=split_name, stats=stats)

        else:
            msg.info(f"{output_file} already exists")
            if self.calculate_stats or self.preprocess_text:
                df = load_dataframe(output_file, self.data_filetype)

        if df is None:
            print("No datasets found")
            return None

        if self.process_pipeline and len(self.process_pipeline) > 0:
            print(f"\nProcessing dataframe with pipeline: {self.process_pipeline}")
            df = apply_pipeline(df, self.process_pipeline, self.pipeline_args)

        if self.calculate_stats and self.summary_info:
            self.summary_info.calculate_stats(df, split_name)
