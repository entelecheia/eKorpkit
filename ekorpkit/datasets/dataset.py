import logging
from pathlib import Path
from pprint import pprint
from ekorpkit import eKonf
from ekorpkit.pipelines.pipe import apply_pipeline
from ekorpkit.io.file import load_dataframe


log = logging.getLogger(__name__)


class Dataset:
    def __init__(self, **args):
        self.args = eKonf.to_dict(args)
        self.name = self.args["name"]
        if isinstance(self.name, list):
            self.name = self.name[0]
        self.verbose = self.args.get("verbose", False)
        self.autoload = self.args.get("autoload", False)
        use_name_as_subdir = args.get("use_name_as_subdir", True)

        self.data_dir = Path(self.args["data_dir"])
        if use_name_as_subdir:
            self.data_dir = self.data_dir / self.name
        self.info_file = self.data_dir / f"info-{self.name}.yaml"
        self.info = eKonf.load(self.info_file) if self.info_file.is_file() else {}
        if self.info:
            if self.verbose:
                log.info(f"Loaded info file: {self.info_file}")
            self.args = eKonf.to_dict(eKonf.merge(self.args, self.info))
            self.info = eKonf.to_dict(self.info)

        if self.verbose:
            log.info(f"Intantiating a dataset {self.name} with a config:")
            pprint(eKonf.to_dict(self.args))

        self.filetype = self.args.get("filetype", "csv")
        self.data_files = self.args.get("data_files", None)
        if self.data_files is None:
            self.data_files = {
                "train": f"{self.name}-train.{self.filetype}",
                "dev": f"{self.name}-dev.{self.filetype}",
                "test": f"{self.name}-test.{self.filetype}",
            }

        self.description = self.args.get("description", "")
        self.license = self.args.get("license", "")
        self.column_info = self.args.get("column_info")
        if self.column_info is None:
            raise ValueError("Column info can't be None")

        self._id_key = "id"
        self._keys = self.column_info["keys"]
        self._id_keys = self._keys[self._id_key]
        if isinstance(self._id_keys, str):
            self._id_keys = [self._id_keys]
        self._data_keys = self.column_info.get("data", None)

        self.pipeline_args = self.args.get("pipeline", {})
        self.transform_pipeline = self.pipeline_args.get("_transform_", [])
        self.process_pipeline = self.pipeline_args.get("_pipeline_", [])
        if self.transform_pipeline is None:
            self.transform_pipeline = []
        if self.process_pipeline is None:
            self.process_pipeline = []

        self.splits = {}
        self._loaded = False

        if self.autoload:
            self.load()

    def __str__(self):
        classname = self.__class__.__name__
        s = f"{classname} : {self.name}"
        return s

    def __getitem__(self, split):
        return self.splits[split]

    @property
    def ID(self):
        return self._id_key

    @property
    def IDs(self):
        return self._id_keys

    @property
    def DATA(self):
        return list(self._data_keys.keys())

    def load(self):
        if self._loaded:
            return
        for split, data_file in self.data_files.items():
            data_file = self.data_dir / data_file
            df = load_dataframe(data_file, dtype=self._data_keys)
            if self.process_pipeline and len(self.process_pipeline) > 0:
                df = apply_pipeline(df, self.process_pipeline, self.pipeline_args)
            self.splits[split] = df
        self._loaded = True
