import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable

from model.utils.config import cfg
from model.utils.network import _smooth_l1_loss
from .graph_conv_score_unit import _GraphConvolutionLayer_Collect
from .graph_conv_score_unit import _GraphConvolutionLayer_Update
import numpy as np
import math
import pdb
import time

class _GraphConvolutionLayer(nn.Module):
    """ graph convolutional layer """
    def __init__(self, dim_obj, dim_att, dim_rel):
        super(_GraphConvolutionLayer, self).__init__()

        self.gcn_collect = _GraphConvolutionLayer_Collect(dim_obj, dim_att, dim_rel)
        self.gcn_update = _GraphConvolutionLayer_Update(dim_obj, dim_att, dim_rel)


    def forward(self, score_obj, score_att, score_rel, map_obj_obj, map_obj_att, map_obj_rel):
        # Inputs:
            # feat_obj (N x D): N object features
            # feat_att (N X D): N attribute features
            # feat_rel (M x D): M relation features, normally M = N
            # map_obj_att (N X 1): Connectivity from objects to attributes, all entries are 1 normally
            # map_obj_obj (N X N): Connectivity among obhjects, computed based on overlaps, asymmetric normally
            # map_obj_rel (N X M x 2): Connectivity from objects to relations, also asymmetric normally
        # Outputs:
            # feat_obj_out (N X D): N object features after processing
            # feat_att_out (N X D): N attribute features after processing
            # feat_rel_out (M X D): M relation features after processing
        # updating attriutes representations
        # pseudo code: feat_att_out = f(feat_att + feat_obj * W_{obj->att} * map_obj_att)
        map_att_obj = map_obj_att.t()
        source = self.gcn_collect(score_att, score_obj, map_att_obj, cfg.COLLECT_ATT_FROM_OBJ)
        score_att_updated = self.gcn_update(score_att, source, cfg.UPDATE_ATT_FROM_ALL)

        # updating objects representations
        # pseudo code: feat_obj_out = feat_obj + f(feat_att * W_{att->obj} * map_att_obj)
        # pseudo code: feat_obj_out = feat_obj_out + f(map_obj_obj * feat_obj * W_{obj-obj} )
        # pseudo code: feat_obj_out[sub] = feat_obj_out[sub] + f(map_obj_rel * feat_rel * W_{rel->sub})
        # pseudo code: feat_obj_out[obj] = feat_obj_out[obj] + f(map_obj_rel' * feat_rel * W_{rel->obj})
        # pseudo code: feat_obj_out = g(feat_obj_out)
        source_att = self.gcn_collect(score_obj, score_att, map_obj_att, cfg.COLLECT_OBJ_FROM_ATT)
        source_obj = self.gcn_collect(score_obj, score_obj, map_obj_obj, cfg.COLLECT_OBJ_FROM_OBJ)
        map_sobj_rel = map_obj_rel[:, :, 0]
        # map_sobj_rel_sum = map_sobj_rel.sum(1)
        # map_sobj_rel = map_sobj_rel / (map_sobj_rel_sum + 1)
        map_oobj_rel = map_obj_rel[:, :, 1]
        # map_oobj_rel_sum = map_oobj_rel.sum(1)
        # map_oobj_rel = map_oobj_rel / (map_oobj_rel_sum + 1)
        source_rel_sub = self.gcn_collect(score_obj, score_rel, map_sobj_rel, cfg.COLLECT_SOBJ_FROM_REL)
        source_rel_obj = self.gcn_collect(score_obj, score_rel, map_oobj_rel, cfg.COLLECT_OOBJ_FROM_REL)
        source2obj_all = (source_att + source_obj + source_rel_sub + source_rel_obj) / 4
        score_obj_updated = self.gcn_update(score_obj, source2obj_all, cfg.UPDATE_OBJ_FROM_ALL)

        # updating relation representatiosn
        # pseudo code: feat_rel_out[sub] = feat_rel[sub] + f(map_obj_rel[sub] * feat_obj * W_{obj->rel})
        # pseudo code: feat_rel_out[obj] = feat_rel[obj] + f(map_obj_rel[obj] * feat_obj * W_{sub->rel})
        # pseudo code: feat_rel_out = g(feat_rel_out)
        map_rel_sobj = map_obj_rel[:, :, 0].t()
        # map_rel_sobj_sum = map_rel_sobj.sum(1)
        # map_rel_sobj = map_rel_sobj / (map_rel_sobj_sum  + 1)
        map_rel_oobj = map_obj_rel[:, :, 1].t()
        # map_rel_oobj_sum = map_rel_oobj.sum(1)
        # map_rel_oobj = map_rel_oobj / (map_rel_oobj_sum + 1)
        source_obj_sub = self.gcn_collect(score_rel, score_obj, map_rel_sobj, cfg.COLLECT_REL_FROM_SOBJ)
        source_obj_obj = self.gcn_collect(score_rel, score_obj, map_rel_oobj, cfg.COLLECT_REL_FROM_OOBJ)
        source2rel_all = (source_obj_sub + source_obj_obj) / 2
        score_rel_updated = self.gcn_update(score_rel, source2rel_all, cfg.UPDATE_REL_FROM_ALL)

        return score_obj_updated, score_att_updated, score_rel_updated
