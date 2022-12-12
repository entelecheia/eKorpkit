import logging
import random
import inspect
from omegaconf import DictConfig
from pathlib import Path
from pydantic import (
    BaseModel,
    validator,
)
from typing import (
    Any,
    Optional,
    Union,
)
from ekorpkit import eKonf
from .base import Environments, Secrets, ProjectConfig


logger = logging.getLogger(__name__)


class PathConfig(BaseModel):
    task_name: str = "default-task"
    root: str = None
    batch_name: str = None
    verbose: bool = False

    class Config:
        extra = "ignore"

    def __init__(self, **data: Any):
        if not data:
            data = eKonf.compose("path=__batch__")
            logger.info(
                "There are no arguments to initilize a config, using default config."
            )
        super().__init__(**data)

    @property
    def root_dir(self):
        return Path(self.root)

    @property
    def output_dir(self):
        return self.root_dir / "outputs"

    @property
    def batch_dir(self):
        return self.output_dir / self.batch_name

    @property
    def library_dir(self):
        return self.root_dir / "libs"

    @property
    def data_dir(self):
        return self.root_dir / "data"

    @property
    def model_dir(self):
        return self.root_dir / "models"

    @property
    def cache_dir(self):
        return self.root_dir / "cache"

    @property
    def tmp_dir(self):
        return self.root_dir / "tmp"


class BaseBatchConfig(BaseModel):
    batch_name: str
    batch_num: int = None
    output_dir: Path = Path.cwd() / "outputs"
    output_suffix: str = None
    output_extention: Optional[str] = ""
    random_seed: bool = True
    seed: int = None
    resume_run: bool = False
    resume_latest: bool = False
    num_workers: int = 1
    device: str = "cpu"
    num_devices: Optional[int] = None
    config_yaml = "config.yaml"
    config_json = "config.json"
    config_dirname = "configs"
    verbose: Union[bool, int] = False

    def __init__(self, **data):
        if not data:
            data = eKonf.compose("batch")
            logger.info(
                f"There is no batch in the config, using default batch: {data.batch_name}"
            )
        super().__init__(**data)
        self.init_batch_num()

    def init_batch_num(self):
        if self.batch_num is None:
            num_files = len(list(self.config_dir.glob(self.config_filepattern)))
            if self.resume_latest:
                self.batch_num = num_files - 1
            else:
                self.batch_num = num_files
        if self.verbose:
            logger.info(
                f"Init batch number - Batch name: {self.batch_name}, Batch num: {self.batch_num}"
            )

    @validator("seed")
    def _validate_seed(cls, v, values):
        if values["random_seed"] or v is None or v < 0:
            random.seed()
            seed = random.randint(0, 2**32 - 1)
            if values.get("verbose"):
                logger.info(f"Setting seed to {seed}")
            return seed
        return v

    @validator("output_extention")
    def _validate_output_extention(cls, v):
        if v:
            return v.strip(".")
        else:
            return ""

    @property
    def batch_dir(self):
        batch_dir = self.output_dir / self.batch_name
        batch_dir.mkdir(parents=True, exist_ok=True)
        return batch_dir

    @property
    def config_dir(self):
        config_dir = self.batch_dir / self.config_dirname
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    @property
    def file_prefix(self):
        return f"{self.batch_name}({self.batch_num})"

    @property
    def output_file(self):
        if self.output_suffix:
            return f"{self.file_prefix}_{self.output_suffix}.{self.output_extention}"
        else:
            return f"{self.file_prefix}.{self.output_extention}"

    @property
    def config_filename(self):
        return f"{self.file_prefix}_{self.config_yaml}"

    @property
    def config_jsonfile(self):
        return f"{self.file_prefix}_{self.config_json}"

    @property
    def config_filepattern(self):
        return f"{self.batch_name}(*)_{self.config_yaml}"

    @property
    def config_filepath(self):
        return self.config_dir / self.config_filename

    @property
    def config_jsonpath(self):
        return self.config_dir / self.config_jsonfile


class BaseBatchModel(BaseModel):
    config_name: str = None
    config_group: str = None
    name: str
    path: PathConfig = None
    batch: BaseBatchConfig = None
    project: ProjectConfig = None
    module: DictConfig = None
    auto: Union[DictConfig, str] = None
    autoload: bool = False
    version: str = "0.0.0"
    _config_: DictConfig = None
    _initial_config_: DictConfig = None

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"
        validate_assignment = False
        exclude = {
            "_config_",
            "_initial_config_",
            "__data__",
            "path",
            "module",
            "secret",
            "auto",
            "project",
        }
        include = {}
        underscore_attrs_are_private = True
        property_set_methods = {
            "name": "set_batch_name",
            "batch_name": "set_batch_name",
            "batch_num": "set_batch_num",
            "output_dir": "set_output_dir",
            "root_dir": "set_root_dir",
        }

    def __init__(self, config_group=None, root_dir=None, **args):
        if config_group is not None:
            args = eKonf.merge(eKonf.compose(config_group), args)
        else:
            args = eKonf.to_config(args)
        super().__init__(**args)

        object.__setattr__(self, "_config_", args)
        object.__setattr__(self, "_initial_config_", args.copy())
        self.initialize_configs(root_dir=root_dir)

    def __setattr__(self, key, val):
        super().__setattr__(key, val)
        method = self.__config__.property_set_methods.get(key)
        if method is not None:
            getattr(self, method)(val)

    def set_root_dir(self, root_dir: Union[str, Path]):
        path = self.config.path
        if path is None:
            path = eKonf.compose("path=_batch_")
            logger.info(
                f"There is no path in the config, using default path: {path.root}"
            )
            self._config_.path = path
        if root_dir is not None:
            path.root = str(root_dir)
        self.path = PathConfig(**path)
        if self.path.verbose:
            eKonf.print(self.path.dict())
        self.output_dir = self.path.output_dir

    def set_output_dir(self, val):
        self._config_.batch.output_dir = str(val)
        self.batch.output_dir = Path(val)

    def set_batch_name(self, val):
        self._config_.batch.batch_name = val
        self._config_.name = val
        self.batch.batch_name = val
        if self.name is None or self.name != val:
            self.name = val
        self.initialize_configs(name=val)

    def set_batch_num(self, val):
        self._config_.batch.batch_num = val
        self.batch.batch_num = val

    def initialize_configs(
        self, root_dir=None, batch_config_class=BaseBatchConfig, **kwargs
    ):
        self.root_dir = root_dir

        self.batch = batch_config_class(**self.config.batch)
        self.batch_num = self.batch.batch_num
        if self.project.init_huggingface_hub:
            self.secrets.init_huggingface_hub()
        logger.info(
            f"Initalized batch: {self.batch_name}({self.batch_num}) in {self.root_dir}"
        )

    @property
    def config(self):
        return self._config_

    @property
    def root_dir(self) -> Path:
        return Path(self.path.root)

    @property
    def output_dir(self):
        return self.path.output_dir

    @property
    def envs(self):
        return Environments()

    @property
    def secrets(self):
        return Secrets()

    @property
    def batch_name(self):
        return self.batch.batch_name

    @property
    def batch_num(self):
        return self.batch.batch_num

    @property
    def project_name(self):
        return self.project.project_name

    @property
    def project_dir(self):
        return Path(self.project.project_dir)

    @property
    def workspace_dir(self):
        return Path(self.project.workspace_dir)

    @property
    def seed(self):
        return self.batch.seed

    @property
    def batch_dir(self):
        return self.batch.batch_dir

    @property
    def data_dir(self):
        return self.path.data_dir

    @property
    def model_dir(self):
        return self.path.model_dir

    @property
    def cache_dir(self):
        cache_dir = Path(self.project.path.cache)
        if cache_dir is None:
            cache_dir = self.output_dir / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
        return Path(cache_dir)

    @property
    def library_dir(self):
        return self.path.library_dir

    @property
    def verbose(self):
        return self.batch.verbose

    @property
    def device(self):
        return self.batch.device

    @property
    def num_devices(self):
        return self.batch.num_devices

    def autorun(self):
        return eKonf.methods(self.auto, self)

    def save_config(
        self,
        config=None,
        exclude=None,
        include=None,
    ):
        """Save the batch config"""
        if config is not None:
            self._config_ = config
        logger.info(f"Saving config to {self.batch.config_filepath}")
        cfg = eKonf.to_dict(self.config)
        if exclude is None:
            exclude = self.__config__.exclude

        if include:
            args = {}
            if isinstance(include, str):
                include = [include]
            for key in include:
                args[key] = cfg[key]
        else:
            args = cfg
            if exclude:
                if isinstance(exclude, str):
                    exclude = [exclude]
                for key in exclude:
                    args.pop(key, None)
        eKonf.save(args, self.batch.config_filepath)
        self.save_settings(exclude=exclude)
        return self.batch.config_filename

    def save_settings(self, exclude=None, exclude_none=True):
        def dumper(obj):
            if isinstance(obj, DictConfig):
                return eKonf.to_dict(obj)
            return str(obj)

        if exclude is None:
            exclude = self.__config__.exclude
        config = self.dict(exclude=exclude, exclude_none=exclude_none)
        if self.verbose:
            logger.info(f"Saving config to {self.batch.config_jsonpath}")
        eKonf.save_json(config, self.batch.config_jsonpath, default=dumper)

    def load_config(
        self,
        batch_name=None,
        batch_num=None,
        **args,
    ):
        """Load the config from the batch config file"""
        logger.info(
            f"> Loading config for batch_name: {batch_name} batch_num: {batch_num}"
        )
        # self.config.batch.batch_num = batch_num
        if batch_name is None:
            batch_name = self.batch_name

        if batch_num is not None:
            cfg = self._initial_config_.copy()
            self.batch.batch_name = batch_name
            self.batch.batch_num = batch_num
            _path = self.batch.config_filepath
            if _path.is_file():
                logger.info(f"Loading config from {_path}")
                batch_cfg = eKonf.load(_path)
                logger.info("Merging config with the loaded config")
                cfg = eKonf.merge(cfg, batch_cfg)
            else:
                logger.info(f"No config file found at {_path}")
                batch_num = None
        else:
            cfg = self.config

        logger.info(f"Merging config with args: {args}")
        self._config_ = eKonf.merge(cfg, args)

        self.batch_num = batch_num
        self.batch_name = batch_name

        return self.config

    def show_config(self, batch_name=None, batch_num=None):
        cfg = self.load_config(batch_name, batch_num)
        eKonf.print(cfg)

    def load_modules(self):
        """Load the modules"""
        if self.module.get("modules") is None:
            logger.info("No modules to load")
            return
        library_dir = self.library_dir
        for module in self.module.modules:
            name = module.name
            libname = module.libname
            liburi = module.liburi
            specname = module.specname
            libpath = library_dir / libname
            syspath = module.get("syspath")
            if syspath is not None:
                syspath = library_dir / syspath
            eKonf.ensure_import_module(name, libpath, liburi, specname, syspath)

    def reset(self, objects=None):
        """Reset the memory cache"""
        if isinstance(objects, list):
            for obj in objects:
                del obj
        try:
            from ekorpkit.utils.gpu import GPUMon

            GPUMon.release_gpu_memory()
        except ImportError:
            pass
