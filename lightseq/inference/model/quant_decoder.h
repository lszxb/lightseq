#pragma once

#include <cublas_v2.h>
#include <cuda.h>
#include <cuda_runtime.h>
#include <curand_kernel.h>
#include <thrust/functional.h>
#include <thrust/sequence.h>
#include <cublasLt.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iostream>
#include <string>
#include <unistd.h>

#include "../proto/quant_transformer_weight.h"
#include "../tools/util.h"
#include "cublas_algo_map.h"

/**
@file
QuantTransformer decoder, composed by gemm lib and
  custom cuda kernel function
*/
namespace lightseq {
namespace cuda {

template <OperationType OpType_>
class QuantDecoder {
 private:
  typedef OperationTypeTraits<OpType_> _optraits;
  typedef typename _optraits::DataType _DataType;
  const cudaDataType_t _computeType = _optraits::computeType;
  const cudaDataType_t _AType = _optraits::AType;
  const cudaDataType_t _BType = _optraits::BType;
  const cudaDataType_t _CType = _optraits::CType;
  // private mem function
  void project_encoder_output();
  bool run_step();
  void embedding();
  void decoder_stack();
  void self_attention();
  void encdec_attention();
  void ffn_add_norm();
  bool sample();
  bool beam_search();
  void update_new_seq_probs();
  bool topk_greedy_search();

  // constructor init var
  const int _max_batch_size;
  const int _max_thread_per_block;
  int _h_can_num_batch;
  int _h_unfinished;
  size_t _cub_sort_buffer_bytes;
  QuantTransformerWeight<OpType_>& _tw;
  cudaStream_t _stream;
  cublasHandle_t _hd;
  cublasLtHandle_t _cublas_lt_handle;
  cublasAlgoMap _algo_map;
  const bool _sm_gt_eq_80;

  const int* _p_d_padding_mask;
  const _DataType* _p_d_encoder_output;
  int* _p_d_sample_unfinished;
  curandState* _p_d_curandstate;  //[batch_size]

  std::vector<float> _h_alive_seq_probs;
  std::vector<float> _h_length_norm;
  float* _p_d_alive_seq_probs;
  float* _p_d_can_score;
  int* _p_d_can_idx;
  int* _p_d_can_num;
  int* _p_d_alive_seq;
  int* _p_d_alive_seq_buf;
  _DataType* _p_d_cur_step_query;
  // cur step's projected query-key-value in self atten, one pointer for one
  // decoder layer device memory in [batch_size, beam_size, 3, hidden_size]
  // format
  _DataType* _p_d_self_step_qkv;
  // key re-arrange for batch_geem in self atten, one pointer for one decoder
  // layer device memory in [batch_size, beam_size, head_num, dim_per_head,
  // max_step] format
  std::vector<_DataType*> _p_d_self_k_bgeem;
  _DataType** _p_d_self_k_bgeem1;
  _DataType** _p_d_self_k_bgeem2;
  // value re-arrange for batch_geem in self atten, one pointer for one decoder
  // layer device memory in [batch_size, beam_size, head_num, max_step,
  // dim_per_head] format
  std::vector<_DataType*> _p_d_self_v_bgeem;
  _DataType** _p_d_self_v_bgeem1;
  _DataType** _p_d_self_v_bgeem2;
  // key re-arrange for batch_geem in encdec atten, one pointer for one decoder
  // layer device memory in [batch_size, head_num, dim_per_head, batch_seq_len]
  // format
  std::vector<_DataType*> _p_d_encdec_k_bgeem;
  // value re-arrange for batch_geem in encdec atten, one pointer for one
  // decoder layer device memory in [batch_size, head_num, batch_seq_len,
  // dim_per_head] format
  std::vector<_DataType*> _p_d_encdec_v_bgeem;
  _DataType* _p_d_query_buf1;
  _DataType* _p_d_query_buf2;
  _DataType* _p_d_c;
  _DataType* _p_d_encoder_out_buf;

  int8_t* _int8_ffn_in_buf;
  int32_t* _int32_ffn_out_buf;
  int8_t* _int8_ffn_out_buf;
  std::vector<int8_t*> _p_d_self_k_cache;
  std::vector<int8_t*> _p_d_self_v_cache;
  int8_t** _p_d_self_k_cache1;
  int8_t** _p_d_self_k_cache2;
  int8_t** _p_d_self_v_cache1;
  int8_t** _p_d_self_v_cache2;

  int _batch_size;
  int _batch_seq_len;
  int _batch_token_num;
  int _layer_id;
  int _weight_offset;
  int _step_token_num;
  int _batch_max_decode_length;
  bool _is_sampling;
  bool _is_benchmark;

  const std::vector<const _DataType*>& _p_d_trg_emb_wei;  // size: 7
  const std::vector<const _DataType*>&
      _p_d_dec_wei;  // size: 18 * dec_layer_num
  std::vector<const _DataType*> _p_device_wei;
  std::vector<const _DataType*> _p_device_emb;

  std::vector<int8_t*> _int8_p_d_dec_wei;
  int8_t* _int8_p_d_trg_emb_wei;
  int8_t* _int8_p_d_trg_emb_bottom_wei;
  const float _quant_range = 127;
  const float _trg_emb_clip_max;
  const float _output_ln_clip_max;
  const float _logits_clip_max;
  const std::vector<float> _encode_output_project_kernel_kv_clip_max;
  const std::vector<float> _dec_clip_max;  // size: 19 * dec_layer_num
  std::vector<_DataType*> _scaled_ffn2_colsum;

  const _DataType _type_one;
  const _DataType _type_zero;

  const int32_t _ione;
  const int32_t _izero;

  const float _fzero;
  const _DataType
      _atten_scaler;  // scaling factor of Scaled Dot-Product Attention
  const long _layer_size_encdec_k;
  const long _layer_size_self_k;
  const std::set<std::string> kSamplingMethods = {"beam_search", "topk", "topp",
                                                  "topk_greedy"};

 public:
  QuantDecoder(int max_batch_size, const int* p_d_padding_mask,
               const _DataType* p_d_encoder_output, int* p_d_result,
               QuantTransformerWeight<OpType_>& tw, cudaStream_t stream,
               cublasHandle_t hd, bool output_topk = false,
               const int* p_d_lang_id = nullptr);
  void init_buffer();
  std::string check();
  void run_one_infer(int batch_size, int batch_seq_len);
  void benchmark_mode(bool is_benchmark);
  int _cur_step;
  float* _p_d_alive_seq_score;
  bool _output_topk;
  int* _p_d_result;
  const int* _p_d_lang_id;
};

}  // namespace cuda
}  // namespace lightseq
