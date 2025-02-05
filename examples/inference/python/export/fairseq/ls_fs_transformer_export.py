"""
Export Fairseq Transformer models training with LightSeq modules to protobuf/hdf5 format.
Refer to the `examples/training/fairseq` directory for more training details.
"""
import torch
# import h5py
from export.proto.transformer_pb2 import Transformer
from lightseq.training import (
    export_ls_config,
    export_ls_embedding,
    export_ls_encoder,
    export_ls_decoder,
)
import lightseq.inference as lsi
from export.util import parse_args, save_model


def _extract_weight(state_dict):
    encoder_state_dict = {}
    decoder_state_dict = {}
    for k in state_dict:
        if k.startswith("encoder."):
            encoder_state_dict[k] = state_dict[k]
        if k.startswith("decoder."):
            decoder_state_dict[k] = state_dict[k]
    return encoder_state_dict, decoder_state_dict


def export_fs_weights(transformer, state_dict, args):
    enc_norm_w = state_dict["encoder.layer_norm.weight"].flatten().tolist()
    enc_norm_b = state_dict["encoder.layer_norm.bias"].flatten().tolist()
    dec_norm_w = state_dict["decoder.layer_norm.weight"].flatten().tolist()
    dec_norm_b = state_dict["decoder.layer_norm.bias"].flatten().tolist()
    emb_size = state_dict["decoder.embed_tokens.para"].size(0) - 1
    assert emb_size % args.decoder_embed_dim == 0
    dec_shared_b = torch.zeros(emb_size // args.decoder_embed_dim).flatten().tolist()
    transformer.src_embedding.norm_scale[:] = enc_norm_w
    transformer.src_embedding.norm_bias[:] = enc_norm_b
    transformer.trg_embedding.norm_scale[:] = dec_norm_w
    transformer.trg_embedding.norm_bias[:] = dec_norm_b
    transformer.trg_embedding.shared_bias[:] = dec_shared_b


def export_ls_fs_transformer(model_path, pb_path, hdf5_path, hdf5):
    with open(model_path, "rb") as fin:
        ckpt_file = torch.load(fin)
    args = ckpt_file["args"]
    state_dict = ckpt_file["model"]

    transformer = Transformer()
    encoder_state_dict, decoder_state_dict = _extract_weight(state_dict)
    export_ls_embedding(
        transformer, encoder_state_dict, 300, args.encoder_embed_dim, True, save_pb=True
    )
    export_ls_embedding(
        transformer,
        decoder_state_dict,
        300,
        args.decoder_embed_dim,
        False,
        save_pb=True,
    )
    export_ls_encoder(
        transformer,
        encoder_state_dict,
        args.encoder_embed_dim,
        args.encoder_ffn_embed_dim,
        save_pb=True,
    )
    export_ls_decoder(
        transformer,
        decoder_state_dict,
        args.decoder_embed_dim,
        args.decoder_ffn_embed_dim,
        args.decoder_layers,
        save_pb=True,
    )
    export_fs_weights(transformer, state_dict, args)
    export_ls_config(
        transformer,
        args.encoder_attention_heads,
        1,
        2,
        2,
        args.encoder_layers,
        args.decoder_layers,
        save_pb=True,
    )

    save_path = save_model(transformer, pb_path, hdf5_path, hdf5)
    return save_path


if __name__ == "__main__":
    #ckpt_path = "/mnt/E/NLP/model/scratch_fairseq_novel_reverse_20220302/checkpoint_best.pt"
    args = parse_args()
    model_name = ".".join(args.model.split(".")[:-1])
    pb_path = f"{model_name}.pb"
    hdf5_path = f"{model_name}.hdf5"

    # # print("export to pb model >>>>>>")
    # # export_ls_fs_transformer(args.model, pb_path)
    # print("export to hdf5 model >>>>>>")
    # export_ls_fs_transformer(args.model, hdf5_path, save_pb=False)
    # src = [[21, 5]]
    # # src = [[463, 10184, 120, 4, 2]]
    # # src = [[63, 47, 65, 1507, 88, 74, 10, 2057, 362, 9, 284, 6, 2, 1, 1, 1]]
    # # pb_model = lsi.Transformer(pb_path, 8)
    # # pb_output = pb_model.infer(src)
    # hdf5_model = lsi.Transformer(hdf5_path, 8)
    # hdf5_output = hdf5_model.infer(src)
    # # Expected result: [23, 550, 34, 118, 148, 2939, 4, 42, 32, 37, 6, 224, 10, 179, 5, 2]
    # # print("pb results:", pb_output)
    # print("hdf5 results:", hdf5_output)

    path = export_ls_fs_transformer(args.model, pb_path, hdf5_path, args.hdf5)
    src = [[63, 47, 65, 1507, 88, 74, 10, 2057, 362, 9, 284, 6, 2, 1, 1, 1]]
    model = lsi.Transformer(path, 8)
    output = model.infer(src)
    # Expected result: [23, 550, 34, 118, 148, 2939, 4, 42, 32, 37, 6, 224, 10, 179, 5, 2]
    print("results:", output)
