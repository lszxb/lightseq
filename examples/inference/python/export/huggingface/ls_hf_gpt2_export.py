"""
Export Hugging Face GPT2 models to hdf5 format.
"""
import os
import h5py
import numpy as np
from collections import OrderedDict
import torch
from lightseq.training.ops.pytorch.export import export_ls_encoder, fill_hdf5_layer
from export.util import parse_args

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"


"""
For the mapping dictionary: key is the value of the proto parameter,
value is a powerful expression, each && split tensor name of the matching path or expression.

The sub-pattern of the path is separated by spaces, and the expression starts with a expression_.
You can operate separately on each tensor and support multiple expressions. Multiple matching paths
and the expression will finally be concatenated on axis = -1.
"""
src_emb_mapping_dict = OrderedDict(
    {
        "norm_scale": "ln_f weight",
        "norm_bias": "ln_f bias",
        "token_embedding": "wte weight",
    }
)


def extract_gpt_weights(
    output_file,
    model_dir,
    head_num,
    generation_method,
    topk=1,
    topp=0.75,
    # default eos_id from https://huggingface.co/transformers/model_doc/gpt2.html#gpt2lmheadmodel
    eos_id=50256,
    pad_id=50257,
    max_step=50,
    extra_decode_length=0,
):
    # load var names
    state_dict = torch.load(model_dir, "cpu")
    var_name_list = list(state_dict.keys())

    # initialize output file
    print("Saving model to hdf5...")
    print("Writing to {0}".format(output_file))
    hdf5_file = h5py.File(output_file, "w")

    wte = state_dict["transformer.wte.weight"]
    emb_dim = wte.shape[1]
    layer_nums = 0
    for name in var_name_list:
        if name.endswith("para"):
            layer_nums += 1

    export_ls_encoder(hdf5_file, state_dict, emb_dim, emb_dim * 4, False)

    # fill src_embedding - except for position embedding
    fill_hdf5_layer(
        var_name_list,
        state_dict,
        hdf5_file,
        "src_embedding/",
        src_emb_mapping_dict,
    )

    # special handling for position embedding
    position_emb = state_dict["transformer.wpe.weight"]
    _max_allowed_step, _ = position_emb.shape
    if max_step > _max_allowed_step:
        print(f"max_step {max_step} exceed max allowed step, abort.")
        return
    # truncate position embedding for max_step
    position_emb = position_emb[:max_step, :]
    print(
        f"processed position_embedding with max_step constriant, shape: {position_emb.shape}"
    )
    position_emb = position_emb.flatten().tolist()
    hdf5_file.create_dataset(
        "src_embedding/position_embedding", data=position_emb, dtype="f4"
    )

    # save number of layers metadata
    hdf5_file.create_dataset("model_conf/n_encoder_stack", data=layer_nums, dtype="i4")
    # fill in model_conf
    hdf5_file.create_dataset("model_conf/head_num", data=head_num, dtype="i4")
    hdf5_file.create_dataset("model_conf/src_padding_id", data=pad_id, dtype="i4")
    hdf5_file.create_dataset(
        "model_conf/sampling_method",
        data=np.array([ord(c) for c in generation_method]).astype(np.int8),
        dtype="i1",
    )
    hdf5_file.create_dataset("model_conf/topp", data=topp, dtype="f4")
    hdf5_file.create_dataset("model_conf/topk", data=topk, dtype="i4")
    hdf5_file.create_dataset("model_conf/eos_id", data=eos_id, dtype="i4")
    hdf5_file.create_dataset(
        "model_conf/extra_decode_length", data=extra_decode_length, dtype="i4"
    )

    hdf5_file.close()
    # read-in again to double check
    hdf5_file = h5py.File(output_file, "r")

    def _print_pair(key, value):
        if key == "sampling_method":
            value = "".join(map(chr, value[()]))
        else:
            value = value[()]
        print(f"{key}: {value}")

    list(map(lambda x: _print_pair(*x), hdf5_file["model_conf"].items()))


if __name__ == "__main__":
    args = parse_args()
    model_name = ".".join(args.model.split(".")[:-1])
    hdf5_path = f"{model_name}.hdf5"

    if args.generation_method not in ["topk", "topp", "ppl"]:
        args.generation_method = "topk"

    head_number = 12  # 20 for "gpt2-large"
    topk = 1
    topp = 0.75
    # default eos_id from https://huggingface.co/transformers/model_doc/gpt2.html#gpt2lmheadmodel
    eos_id = 50256
    pad_id = 50257
    max_step = 50
    extra_decode_length = 0  # use positive length to avtivate it
    extract_gpt_weights(
        hdf5_path,
        args.model,
        head_num=head_number,  # layer number
        generation_method=args.generation_method,
        topk=topk,
        topp=topp,
        eos_id=eos_id,
        pad_id=pad_id,
        max_step=max_step,
        extra_decode_length=extra_decode_length,
    )
