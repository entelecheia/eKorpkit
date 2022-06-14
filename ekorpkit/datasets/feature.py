import os
import logging
from ekorpkit import eKonf
from ekorpkit.pipelines.pipe import apply_pipeline
from .dataset import Dataset


log = logging.getLogger(__name__)


class FeatureSet(Dataset):
    """Feature class."""

    def __init__(self, **args):
        super().__init__(**args)

    @property
    def X_train(self):
        if self.train_data is not None:
            return self.train_data[self.COLUMN.X]
        else:
            return None

    @property
    def X_dev(self):
        if self.dev_data is not None:
            return self.dev_data[self.COLUMN.X]
        else:
            return None

    @property
    def X_test(self):
        if self.test_data is not None:
            return self.test_data[self.COLUMN.X]
        else:
            return None

    @property
    def y_train(self):
        if self.train_data is not None:
            return self.train_data[self.COLUMN.Y]
        else:
            return None

    @property
    def y_dev(self):
        if self.dev_data is not None:
            return self.dev_data[self.COLUMN.Y]
        else:
            return None

    @property
    def y_test(self):
        if self.test_data is not None:
            return self.test_data[self.COLUMN.Y]
        else:
            return None

    @property
    def X(self):
        return self.data[self.COLUMN.X]

    @property
    def y(self):
        return self.data[self.COLUMN.Y]

    def load(self):
        if self._loaded:
            return
        for split, data_file in self.data_files.items():
            data_file = os.path.join(self.data_dir, data_file)
            if eKonf.exists(data_file):
                df = eKonf.load_data(data_file, dtype=self.DATATYPEs)
                df = self.COLUMN.init_info(df)
                df = self.COLUMN.append_split(df, split)
                self._splits[split] = df
            else:
                log.info(f"Dataset {self.name} split {split} is empty")
        self._loaded = True

    def build(self):
        data = None
        if self._pipeline_ and len(self._pipeline_) > 0:
            data = apply_pipeline(data, self._pipeline_, self._pipeline_cfg)
        if data is not None:
            log.info(f"Dataset {self.name} built with {len(data)} rows")
        else:
            log.info(f"Dataset {self.name} is empty")

    def persist(self):
        if not self._loaded:
            log.info(f"Dataset {self.name} is not loaded")
            return
        if self.summary_info is None:
            self.summarize()
        for split, data in self._splits.items():
            if data is None:
                continue
            data_file = self.data_files[split]
            eKonf.save_data(
                data,
                data_file,
                base_dir=self.data_dir,
                verbose=self.verbose,
            )
        if self.summary_info is not None:
            self.summary_info.save(info={"column_info": self.COLUMN.INFO})
