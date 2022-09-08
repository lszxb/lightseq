#pragma once
#include "layer.h"
#include "feed_forward_layer.h"
#include "dec_self_attention_layer.h"

namespace lightseq {

template <class T1, class T2>
class TransformerDecoderLayer : public Layer {
 private:
  DecSelfAttentionLayerPtr<T1, T2> _self_attn_layer;
  DecEncAttentionLayerPtr<T1, T2> _enc_attn_layer;
  FeedForwardLayerPtr<T1, T2> _ffn_layer;

 public:
  TransformerDecoderLayer(int layer_id, int max_batch_tokens, int max_seq_len,
                          int hidden_size, int num_heads, int intermediate_size,
                          float attn_prob_dropout_ratio,
                          float activation_dropout_ratio,
                          float hidden_output_dropout_ratio,
                          bool pre_or_postLayerNorm, std::string activation_fn,
                          bool mask_future_tokens, bool is_post_ln = false);
  virtual ~TransformerDecoderLayer() {}

  Variable* operator()(Variable* inp, Variable* inp_mask);

  void before_forward(int batch_size, int seq_len, int step) {
    _self_attn_layer->before_forward(batch_size, seq_len, step);
    _enc_attn_layer->before_forward(batch_size, seq_len);
    _ffn_layer->before_forward(batch_size, seq_len);
  }

  void before_backward() { return; }

  int load_para_and_grad(const T1* para_ptr, T2* grad_ptr);

  int load_params(const std::vector<const T1*>& para_vec, int offset);
};

template class TransformerDecoderLayer<float, float>;
template class TransformerDecoderLayer<__half, __half>;

template <class T1, class T2>
using TransformerDecoderLayerPtr =
    std::shared_ptr<TransformerDecoderLayer<T1, T2>>;

}  // namespace lightseq
