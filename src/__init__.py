# flake8: noqa
from catalyst.dl import registry

from .experiment import Experiment
from .runner import ModelRunner as Runner
from .callbacks import EmbeddingsCriterionCallback
from .model import MultiHeadNet, MultiHeadNetAE, MultiHeadNetVAE

registry.Model(MultiHeadNet)
registry.Model(MultiHeadNetAE)
registry.Model(MultiHeadNetVAE)
registry.Callback(EmbeddingsCriterionCallback)
