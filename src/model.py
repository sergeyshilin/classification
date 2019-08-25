from typing import Dict
from copy import deepcopy

import torch
import torch.nn as nn
from catalyst.contrib.modules import Flatten
from catalyst.contrib.models import SequentialNet
from catalyst.contrib.models.encoder import ResnetEncoder
from catalyst.utils import normal_logprob

from .autoencoder import AEEncoder, AEDecoder, VAEEncoder
from .flow import RealNVP


class MultiHeadNet(nn.Module):
    def __init__(
        self,
        encoder_net: nn.Module,
        head_nets: nn.ModuleList,
        embedding_net: nn.Module = None,
    ):
        super().__init__()
        self.encoder_net = encoder_net
        self.embedding_net = embedding_net or (lambda *args: args)
        self.head_nets = head_nets

    def forward_embeddings(self, x: torch.Tensor):
        features = self.encoder_net(x)
        embeddings = self.embedding_net(features)
        return embeddings

    def forward(self, x: torch.Tensor):
        features = self.encoder_net(x)
        embeddings = self.embedding_net(features)
        result = {"features": features, "embeddings": embeddings}

        for key, head_net in self.head_nets.items():
            result[key] = head_net(embeddings)

        return result

    @classmethod
    def get_from_params(
        cls,
        image_size: int = None,
        encoder_params: Dict = None,
        embedding_net_params: Dict = None,
        heads_params: Dict = None,
    ) -> "MultiHeadNet":

        encoder_params_ = deepcopy(encoder_params)
        embedding_net_params_ = deepcopy(embedding_net_params)
        heads_params_ = deepcopy(heads_params)

        encoder_net = ResnetEncoder(**encoder_params_)

        encoder_input_shape: tuple = (3, image_size, image_size)
        encoder_input = torch.Tensor(torch.randn((1, ) + encoder_input_shape))
        encoder_output = encoder_net(encoder_input)
        enc_size = encoder_output.nelement()
        embedding_net_params_["hiddens"].insert(0, enc_size)

        embedding_net = SequentialNet(**embedding_net_params_)
        emb_size = embedding_net_params_["hiddens"][-1]

        head_kwargs_ = {}
        for key, value in heads_params_.items():
            head_kwargs_[key] = nn.Linear(emb_size, value, bias=True)
        head_nets = nn.ModuleDict(head_kwargs_)

        net = cls(
            encoder_net=encoder_net,
            embedding_net=embedding_net,
            head_nets=head_nets
        )

        return net


class MultiHeadNetAE(MultiHeadNet):
    def forward(self, x: torch.Tensor, deterministic=None):
        x, loc, log_scale = \
            self.encoder_net(x, deterministic=deterministic)

        x_logprob = \
            normal_logprob(loc, log_scale.exp(), x.view(x.shape[0], -1))
        x, x_logprob = self.embedding_net(x, x_logprob)
        result = {
            "embeddings": x,
            "embeddings_loc": loc,
            "embeddings_log_scale": log_scale,
            "embeddings_logprob": x_logprob
        }

        for key, head_net in self.head_nets.items():
            result[key] = head_net(x)

        return result

    @classmethod
    def get_from_params(
        cls,
        image_size: int = None,
        mode: str = None,
        encoder_params: Dict = None,
        embedding_net_params: Dict = None,
        decoder_params: Dict = None,
        heads_params: Dict = None,
    ) -> "MultiHeadNetAE":

        assert mode in ["ae", "vae", "ae_nf", "vae_nf"]

        encoder_params_ = deepcopy(encoder_params)
        heads_params_ = deepcopy(heads_params)

        encoder_net = AEEncoder(**encoder_params_) \
            if mode in ["ae", "ae_nf"] \
            else VAEEncoder(**encoder_params)

        input_shape = (3, image_size, image_size)
        input_t = torch.Tensor(torch.randn((1,) + input_shape))
        output_t = encoder_net(input_t)[0]
        emb_size = output_t.nelement()

        embedding_net = RealNVP(emb_size=emb_size) \
            if mode in ["ae_nf", "vae_nf"] \
            else None

        head_kwargs_ = {
            "decoder": AEDecoder(filters=encoder_net.filters, **decoder_params)
        }
        for key, value in heads_params_.items():
            head_kwargs_[key] = nn.Sequential(
                Flatten(),
                nn.Linear(emb_size, value, bias=True)
            )
        head_nets = nn.ModuleDict(head_kwargs_)

        net = cls(
            encoder_net=encoder_net,
            embedding_net=embedding_net,
            head_nets=head_nets
        )

        return net
