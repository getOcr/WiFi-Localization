###
 # @Descripttion: 
 # @version: 
 # @Contributor: Minjun Lu
 # @Source: Original
 # @LastEditTime: 2023-11-02 02:37:58
### 
CUDA_VISIBLE_DEVICES=7 python -m torch.distributed.launch --nproc_per_node=1 --nnodes=1 --master_port=29937 --use_env train.py --cfg /server19/lmj/github/wifi_localization/config/config.yaml