import pandas as pd
import logging
import sklearn
from scipy.special import softmax
from simpletransformers.classification import ClassificationModel
from abc import abstractmethod
from ekorpkit import eKonf
from ekorpkit.config import BaseBatchModel
from ekorpkit.datasets.config import DataframeConfig
from ekorpkit.base import _Keys as Keys
from .config import (
    ColumnConfig,
    ModelBatchConfig,
    TrainerArgs,
    SimpleModelConfig,
    ClassificationArgs,
)

log = logging.getLogger(__name__)


class SimpleTrainer(BaseBatchModel):
    batch: ModelBatchConfig = None
    trainer: TrainerArgs = None
    dataset: DataframeConfig = None
    model: SimpleModelConfig = None
    columns: ColumnConfig = None
    __model_obj__ = None

    class Config:
        arbitrary_types_allowed = True
        underscore_attrs_are_private = True

    def __init__(self, **args):
        super().__init__(**args)

    @abstractmethod
    def train(self):
        raise NotImplementedError("Must override train")

    @abstractmethod
    def predict_data(self, data: list):
        raise NotImplementedError("Must override predict")

    def pred_path(self, pred_file=None):
        if pred_file is None:
            pred_file = self.batch.pred_file
        return str(self.batch_dir / f"{self.batch.file_prefix}_{pred_file}")

    @property
    def raw_datasets(self):
        return self.dataset.datasets

    @property
    def model_obj(self):
        return self.__model_obj__

    def load_datasets(
        self,
        data=None,
        data_files=None,
        data_dir=None,
        test_split_ratio=0.2,
        seed=None,
        shuffle=None,
        encode_labels=None,
        text_column_name=None,
        label_column_name=None,
    ):
        self.dataset.load_datasets(
            data=data,
            data_files=data_files,
            data_dir=data_dir,
            test_split_ratio=test_split_ratio,
            seed=seed,
            shuffle=shuffle,
            encode_labels=encode_labels,
            text_column_name=text_column_name,
            label_column_name=label_column_name,
        )

        if self.dataset.dev_data is not None:
            self.trainer.evaluate_during_training = True
        else:
            self.trainer.evaluate_during_training = False

    def convert_to_train(self):
        return (
            self.rename_columns(self.dataset.train_data, self.columns.train),
            self.rename_columns(self.dataset.dev_data, self.columns.train),
            self.rename_columns(self.dataset.test_data, self.columns.train),
        )

    def rename_columns(self, data, columns):
        if not columns or data is None:
            log.info("No columns or data to rename")
            return data
        renames = {
            name: key
            for key, name in columns.items()
            if name and name != key and name in data.columns
        }
        log.info(f"Renaming columns: {renames}")
        if renames:
            data = data.copy().rename(columns=renames)
        if self.verbose:
            print(data.head())
        return data

    def convert_to_predict(self, data):
        input_col = self.columns.predict[Keys.INPUT]
        data_to_predict = data[input_col].tolist()
        if self.verbose:
            print(data_to_predict[:5])
        return data_to_predict

    def append_predictions(self, data, preds):
        predicted_column = self.columns.predict[Keys.PREDICTED]
        model_outputs_column = self.columns.predict[Keys.MODEL_OUTPUTS]
        data[predicted_column] = preds[Keys.PREDICTED]
        data[model_outputs_column] = preds[Keys.MODEL_OUTPUTS]
        pred_probs_column = self.columns.predict.get(Keys.PRED_PROBS)
        if pred_probs_column:
            data[pred_probs_column] = preds[Keys.PRED_PROBS]
        return data

    def predict(self, data, **args):
        if args:
            self.columns.predict = args
        data_to_predict = self.convert_to_predict(data)
        preds = self.predict_data(data_to_predict)
        data = self.append_predictions(data, preds)
        return data

    def cross_val_predict(self, cv=5, dev_size=0.2, random_state=1235, shuffle=True):

        splits = self.dataset.cross_val_datasets(
            cv=cv, dev_size=dev_size, random_state=random_state, shuffle=shuffle
        )
        pred_dfs = []
        for i, split in enumerate(splits):
            self.train()
            log.info(f"Predicting split {i}")
            pred_df = self.predict(split)
            pred_dfs.append(pred_df)
        return pd.concat(pred_dfs)

    def eval(self):
        if self.dataset.test_data is None:
            log.warning("No test data found")
            return

        data_to_predict = self.convert_to_predict(self.dataset.test_data)
        preds = self.predict_data(data_to_predict)
        self.pred_data = self.append_predictions(self.dataset.test_data, preds)
        eKonf.save_data(self.pred_data, self.pred_path())
        if self.verbose:
            print(self.pred_data.head())
        # if self._eval_cfg:
        #     self._eval_cfg.labels = self.labels_list
        #     eKonf.instantiate(self._eval_cfg, data=self.pred_data)


class SimpleClassification(SimpleTrainer):
    trainer: ClassificationArgs = None

    def __init__(self, config_name: str = "simple.classification", **args):
        config_group = f"task={config_name}"
        super().__init__(config_name=config_name, config_group=config_group, **args)

    @property
    def label_list(self):
        return self.model_obj.args.labels_list

    @property
    def labels_map(self):
        return self.model_obj.args.labels_map

    @property
    def model_obj(self) -> ClassificationModel:
        if self.__model_obj__ is None:
            self.load_model()
        return self.__model_obj__

    def train(self):

        model_args = self.model
        train_data, dev_data, test_data = self.convert_to_train()

        self.trainer.labels_list = train_data[Keys.LABELS].unique().tolist()
        model_args.num_labels = len(self.trainer.labels_list)

        # Create a NERModel
        model = ClassificationModel(
            model_args.model_type,
            model_args.model_name_or_path,
            num_labels=model_args.num_labels,
            use_cuda=model_args.use_cuda,
            cuda_device=model_args.device,
            args=self.trainer.dict(),
        )

        # Train the model
        model.train_model(
            train_data, eval_df=dev_data, acc=sklearn.metrics.accuracy_score
        )

        # Evaluate the model
        result, model_outputs, wrong_predictions = model.eval_model(
            test_data, acc=sklearn.metrics.accuracy_score
        )
        if self.verbose:
            print(f"Evaluation result: {result}")
            print(f"Wrong predictions: {wrong_predictions[:5]}")
            print(f"num_outputs: {len(model_outputs)}")
            print(f"num_wrong_predictions: {len(wrong_predictions)}")
        self.__model_obj__ = model

    def load_model(self, model_dir=None):
        from simpletransformers.classification import ClassificationModel

        if model_dir is None:
            model_dir = self.trainer.best_model_dir

        self.__model_obj__ = ClassificationModel(self.model.model_type, model_dir)
        # , args=self._model_cfg
        log.info(f"Loaded model from {model_dir}")

    def predict_data(self, data: list):
        predictions, raw_outputs = self.model_obj.predict(data)
        log.info(f"type of raw_outputs: {type(raw_outputs)}")
        prob_outputs = [softmax(output.flatten().tolist()) for output in raw_outputs]
        model_outputs = [dict(zip(self.labels_list, output)) for output in prob_outputs]
        pred_probs = [output.max() for output in prob_outputs]
        log.info(f"raw_output: {raw_outputs[0]}")
        return {
            Keys.PREDICTED.value: predictions,
            Keys.PRED_PROBS.value: pred_probs,
            Keys.MODEL_OUTPUTS.value: model_outputs,
        }
