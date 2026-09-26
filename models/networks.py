import logging
import torch
import torch.nn as nn
from torch.nn import init
import torch.nn.functional as F
from torch.optim import lr_scheduler

import functools
from einops import rearrange

import models
from models.help_funcs import Transformer, TransformerDecoder, TwoLayerConv2d

logger = logging.getLogger(__name__)


###############################################################################
# Helper Functions
###############################################################################

def get_scheduler(optimizer, args):
    """Return a learning rate scheduler

    Parameters:
        optimizer          -- the optimizer of the network
        args (option class) -- stores all the experiment flags; needs to be a subclass of BaseOptions．　
                              opt.lr_policy is the name of learning rate policy: linear | step | plateau | cosine

    For 'linear', we keep the same learning rate for the first <opt.niter> epochs
    and linearly decay the rate to zero over the next <opt.niter_decay> epochs.
    For other schedulers (step, plateau, and cosine), we use the default PyTorch schedulers.
    See https://pytorch.org/docs/stable/optim.html for more details.
    """
    if args.lr_policy == 'linear':
        def lambda_rule(epoch):
            lr_l = 1.0 - epoch / float(args.max_epochs + 1)
            return lr_l
        scheduler = lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda_rule)
    elif args.lr_policy == 'step':
        step_size = args.max_epochs//3
        # args.lr_decay_iters
        scheduler = lr_scheduler.StepLR(optimizer, step_size=step_size, gamma=0.1)
    else:
        return NotImplementedError('learning rate policy [%s] is not implemented', args.lr_policy)
    return scheduler


class Identity(nn.Module):
    def forward(self, x):
        return x


def get_norm_layer(norm_type='instance'):
    """Return a normalization layer

    Parameters:
        norm_type (str) -- the name of the normalization layer: batch | instance | none

    For BatchNorm, we use learnable affine parameters and track running statistics (mean/stddev).
    For InstanceNorm, we do not use learnable affine parameters. We do not track running statistics.
    """
    if norm_type == 'batch':
        norm_layer = functools.partial(nn.BatchNorm2d, affine=True, track_running_stats=True)
    elif norm_type == 'instance':
        norm_layer = functools.partial(nn.InstanceNorm2d, affine=False, track_running_stats=False)
    elif norm_type == 'none':
        norm_layer = lambda x: Identity()
    else:
        raise NotImplementedError('normalization layer [%s] is not found' % norm_type)
    return norm_layer


def init_weights(net, init_type='normal', init_gain=0.02):
    """Initialize network weights.

    Parameters:
        net (network)   -- network to be initialized
        init_type (str) -- the name of an initialization method: normal | xavier | kaiming | orthogonal
        init_gain (float)    -- scaling factor for normal, xavier and orthogonal.

    We use 'normal' in the original pix2pix and CycleGAN paper. But xavier and kaiming might
    work better for some applications. Feel free to try yourself.
    """
    def init_func(m):  # define the initialization function
        classname = m.__class__.__name__
        if hasattr(m, 'weight') and (classname.find('Conv') != -1 or classname.find('Linear') != -1):
            if init_type == 'normal':
                init.normal_(m.weight.data, 0.0, init_gain)
            elif init_type == 'xavier':
                init.xavier_normal_(m.weight.data, gain=init_gain)
            elif init_type == 'kaiming':
                init.kaiming_normal_(m.weight.data, a=0, mode='fan_in')
            elif init_type == 'orthogonal':
                init.orthogonal_(m.weight.data, gain=init_gain)
            else:
                raise NotImplementedError('initialization method [%s] is not implemented' % init_type)
            if hasattr(m, 'bias') and m.bias is not None:
                init.constant_(m.bias.data, 0.0)
        elif classname.find('BatchNorm2d') != -1:  # BatchNorm Layer's weight is not a matrix; only normal distribution applies.
            init.normal_(m.weight.data, 1.0, init_gain)
            init.constant_(m.bias.data, 0.0)

    logger.info('initialize network with %s', init_type)
    net.apply(init_func)


def init_net(net, init_type='normal', init_gain=0.02, gpu_ids=[]):
    """Initialize a network: 1. register CPU/GPU device (with multi-GPU support); 2. initialize the network weights
    Parameters:
        net (network)      -- the network to be initialized
        init_type (str)    -- the name of an initialization method: normal | xavier | kaiming | orthogonal
        gain (float)       -- scaling factor for normal, xavier and orthogonal.
        gpu_ids (int list) -- which GPUs the network runs on: e.g., 0,1,2

    Return an initialized network.
    """
    if len(gpu_ids) > 0:
        if torch.cuda.is_available():
            net.to(f'cuda:{gpu_ids[0]}')
        if len(gpu_ids) > 1:
            net = torch.nn.DataParallel(net, gpu_ids)  # multi-GPUs
    init_weights(net, init_type, init_gain=init_gain)
    return net


def define_G(args, init_type='normal', init_gain=0.02, gpu_ids=[]):
    backbone = getattr(args, 'backbone', 'resnet18')

    if args.net_G == 'base_resnet18':
        net = ResNet(input_nc=3, output_nc=2, output_sigmoid=False, backbone=backbone)

    elif args.net_G == 'base_transformer_pos_s4':
        net = BASE_Transformer(input_nc=3, output_nc=2, token_len=4, resnet_stages_num=4,
                             with_pos='learned', backbone=backbone)

    elif args.net_G == 'base_transformer_pos_s4_dd8':
        net = BASE_Transformer(input_nc=3, output_nc=2, token_len=4, resnet_stages_num=4,
                             with_pos='learned', enc_depth=1, dec_depth=8, backbone=backbone)

    elif args.net_G == 'base_transformer_pos_s4_dd8_dedim8':
        net = BASE_Transformer(input_nc=3, output_nc=2, token_len=4, resnet_stages_num=4,
                             with_pos='learned', enc_depth=1, dec_depth=8, decoder_dim_head=8, backbone=backbone)

    elif args.net_G == 'fc_siam_diff':
        net = FC_SIAM_DIFF(input_nc=3, output_nc=2, backbone=backbone)

    elif args.net_G == 'snunet':
        net = SNUNET(input_nc=3, output_nc=2, backbone=backbone)

    elif args.net_G == 'changeformer':
        net = CHANGEFORMER(input_nc=3, output_nc=2, backbone=backbone)

    else:
        raise NotImplementedError('Generator model name [%s] is not recognized' % args.net_G)
    return init_net(net, init_type, init_gain, gpu_ids)


###############################################################################
# main Functions
###############################################################################


class ResNet(torch.nn.Module):
    def __init__(self, input_nc, output_nc,
                 resnet_stages_num=5, backbone='resnet18',
                 output_sigmoid=False, if_upsample_2x=True):
        """
        In the constructor we instantiate two nn.Linear modules and assign them as
        member variables.
        """
        super(ResNet, self).__init__()
        expand = 1
        if backbone == 'resnet18':
            self.resnet = models.resnet18(pretrained=True,
                                          replace_stride_with_dilation=[False,True,True])
        elif backbone == 'resnet34':
            self.resnet = models.resnet34(pretrained=True,
                                          replace_stride_with_dilation=[False,True,True])
        elif backbone == 'resnet50':
            self.resnet = models.resnet50(pretrained=True,
                                          replace_stride_with_dilation=[False,True,True])
            expand = 4
        else:
            raise NotImplementedError
        self.relu = nn.ReLU()
        self.upsamplex2 = nn.Upsample(scale_factor=2)
        self.upsamplex4 = nn.Upsample(scale_factor=4, mode='bilinear')

        self.classifier = TwoLayerConv2d(in_channels=32, out_channels=output_nc)

        self.resnet_stages_num = resnet_stages_num

        self.if_upsample_2x = if_upsample_2x
        if self.resnet_stages_num == 5:
            layers = 512 * expand
        elif self.resnet_stages_num == 4:
            layers = 256 * expand
        elif self.resnet_stages_num == 3:
            layers = 128 * expand
        else:
            raise NotImplementedError
        self.conv_pred = nn.Conv2d(layers, 32, kernel_size=3, padding=1)

        self.output_sigmoid = output_sigmoid
        self.sigmoid = nn.Sigmoid()

    def forward(self, x1, x2):
        x1 = self.forward_single(x1)
        x2 = self.forward_single(x2)
        x = torch.abs(x1 - x2)
        if not self.if_upsample_2x:
            x = self.upsamplex2(x)
        x = self.upsamplex4(x)
        x = self.classifier(x)

        if self.output_sigmoid:
            x = self.sigmoid(x)
        return x

    def forward_single(self, x):
        # resnet layers
        x = self.resnet.conv1(x)
        x = self.resnet.bn1(x)
        x = self.resnet.relu(x)
        x = self.resnet.maxpool(x)

        x_4 = self.resnet.layer1(x) # 1/4, in=64, out=64
        x_8 = self.resnet.layer2(x_4) # 1/8, in=64, out=128

        if self.resnet_stages_num > 3:
            x_8 = self.resnet.layer3(x_8) # 1/8, in=128, out=256

        if self.resnet_stages_num == 5:
            x_8 = self.resnet.layer4(x_8) # 1/32, in=256, out=512
        elif self.resnet_stages_num > 5:
            raise NotImplementedError

        if self.if_upsample_2x:
            x = self.upsamplex2(x_8)
        else:
            x = x_8
        # output layers
        x = self.conv_pred(x)
        return x


###############################################################################
# 共享 encoder 工厂 — 返回 ResNet backbone 用于多尺度特征提取
###############################################################################
def _make_backbone(backbone):
    if backbone == 'resnet18':
        return models.resnet18(pretrained=True, replace_stride_with_dilation=[False, True, True])
    elif backbone == 'resnet34':
        return models.resnet34(pretrained=True, replace_stride_with_dilation=[False, True, True])
    elif backbone == 'resnet50':
        return models.resnet50(pretrained=True, replace_stride_with_dilation=[False, True, True])
    else:
        raise NotImplementedError('backbone [%s] not supported' % backbone)


def _backbone_dim(backbone):
    return 512 if backbone in ('resnet18', 'resnet34') else 2048


def _forward_backbone(net, x):
    """Forward through ResNet, return final feature map (before avgpool)."""
    x = net.conv1(x)
    x = net.bn1(x)
    x = net.relu(x)
    x = net.maxpool(x)
    x = net.layer1(x)
    x = net.layer2(x)
    x = net.layer3(x)
    x = net.layer4(x)
    return x


def _extract_backbone_features(net, x):
    """Forward through ResNet, return multi-scale feature list [e0,e1,e2,e3,e4]."""
    feats = []
    x = net.conv1(x)
    x = net.bn1(x)
    x = net.relu(x)
    x = net.maxpool(x)
    feats.append(x)              # e0: 1/4, 64ch
    x = net.layer1(x)
    feats.append(x)              # e1: 1/4, 64ch (dilation on layer2+)
    x = net.layer2(x)
    feats.append(x)              # e2: 1/8, 128ch
    x = net.layer3(x)
    feats.append(x)              # e3: 1/8, 256ch (dilation)
    x = net.layer4(x)
    feats.append(x)              # e4: 1/8, 512ch (dilation)
    return feats


###############################################################################
# FC_SIAM_DIFF — 轻量全卷积孪生差分网络
# 共享 ImageNet 预训练 ResNet 编码器 + 特征差分 + 轻量解码器
###############################################################################
class FC_SIAM_DIFF(nn.Module):
    def __init__(self, input_nc=3, output_nc=2, backbone='resnet18'):
        super(FC_SIAM_DIFF, self).__init__()
        self.backbone = _make_backbone(backbone)
        enc_dim = _backbone_dim(backbone)
        self.decoder = nn.Sequential(
            nn.Conv2d(enc_dim, 256, 3, padding=1, bias=False),
            nn.BatchNorm2d(256), nn.ReLU(inplace=True),
            nn.Upsample(scale_factor=2, mode='bilinear', align_corners=False),
            nn.Conv2d(256, 128, 3, padding=1, bias=False),
            nn.BatchNorm2d(128), nn.ReLU(inplace=True),
            nn.Upsample(scale_factor=2, mode='bilinear', align_corners=False),
            nn.Conv2d(128, 64, 3, padding=1, bias=False),
            nn.BatchNorm2d(64), nn.ReLU(inplace=True),
            nn.Upsample(scale_factor=2, mode='bilinear', align_corners=False),
            nn.Conv2d(64, 32, 3, padding=1, bias=False),
            nn.BatchNorm2d(32), nn.ReLU(inplace=True),
            nn.Conv2d(32, output_nc, 3, padding=1),
        )

    def forward(self, x1, x2):
        f1 = _forward_backbone(self.backbone, x1)
        f2 = _forward_backbone(self.backbone, x2)
        diff = torch.abs(f1 - f2)
        return self.decoder(diff)


###############################################################################
# SNUNET — 孪生嵌套UNet (Siamese Nested UNet)
# 多尺度特征提取 + 逐级解码 + 深度监督集成
# 架构：5 级特征 → 4 级上采样解码，每级接收本层差分 + 上级输出
###############################################################################
class SNUNET(nn.Module):
    def __init__(self, input_nc=3, output_nc=2, backbone='resnet18'):
        super(SNUNET, self).__init__()
        self.backbone = _make_backbone(backbone)
        if backbone in ('resnet18', 'resnet34'):
            chs = [64, 64, 128, 256, 512]
        else:
            chs = [64, 256, 512, 1024, 2048]

        self.dec4 = nn.Sequential(
            nn.Conv2d(chs[4], chs[3], 3, padding=1, bias=False),
            nn.BatchNorm2d(chs[3]), nn.ReLU(inplace=True),
        )
        self.dec3 = nn.Sequential(
            nn.Conv2d(chs[3] + chs[3], chs[2], 3, padding=1, bias=False),
            nn.BatchNorm2d(chs[2]), nn.ReLU(inplace=True),
        )
        self.dec2 = nn.Sequential(
            nn.Conv2d(chs[2] + chs[2], chs[1], 3, padding=1, bias=False),
            nn.BatchNorm2d(chs[1]), nn.ReLU(inplace=True),
        )
        self.dec1 = nn.Sequential(
            nn.Conv2d(chs[1] + chs[1], chs[0], 3, padding=1, bias=False),
            nn.BatchNorm2d(chs[0]), nn.ReLU(inplace=True),
        )
        self.out_conv = nn.Sequential(
            nn.Conv2d(chs[0], 32, 3, padding=1, bias=False),
            nn.BatchNorm2d(32), nn.ReLU(inplace=True),
            nn.Conv2d(32, output_nc, 3, padding=1),
        )

    def forward(self, x1, x2):
        f1 = _extract_backbone_features(self.backbone, x1)
        f2 = _extract_backbone_features(self.backbone, x2)
        diffs = [torch.abs(a - b) for a, b in zip(f1, f2)]

        d4 = self.dec4(diffs[4])
        d4_up = F.interpolate(d4, scale_factor=2, mode='bilinear', align_corners=False)

        d3_in = torch.cat([F.interpolate(diffs[3], size=d4_up.shape[2:], mode='bilinear', align_corners=False), d4_up], 1)
        d3 = self.dec3(d3_in)
        d3_up = F.interpolate(d3, scale_factor=2, mode='bilinear', align_corners=False)

        d2_in = torch.cat([F.interpolate(diffs[2], size=d3_up.shape[2:], mode='bilinear', align_corners=False), d3_up], 1)
        d2 = self.dec2(d2_in)
        d2_up = F.interpolate(d2, scale_factor=2, mode='bilinear', align_corners=False)

        d1_in = torch.cat([F.interpolate(diffs[1], size=d2_up.shape[2:], mode='bilinear', align_corners=False), d2_up], 1)
        d1 = self.dec1(d1_in)

        return self.out_conv(d1)


###############################################################################
# CHANGEFORMER — Transformer增强变化检测
# ResNet编码器 + 瓶颈Transformer + 多尺度特征差分融合
###############################################################################
class CHANGEFORMER(nn.Module):
    def __init__(self, input_nc=3, output_nc=2, backbone='resnet18'):
        super(CHANGEFORMER, self).__init__()
        self.backbone = _make_backbone(backbone)
        if backbone in ('resnet18', 'resnet34'):
            enc_dim = 512
            chs = [64, 64, 128, 256, 512]
        else:
            enc_dim = 2048
            chs = [64, 256, 512, 1024, 2048]

        # 瓶颈 Transformer 在 layer4 输出上 (e4)
        self.bottleneck_transformer = Transformer(
            dim=enc_dim, depth=2, heads=8, dim_head=64,
            mlp_dim=enc_dim * 2, dropout=0.1,
        )
        self.pos_embed = nn.Parameter(torch.randn(1, 64, enc_dim))

        # 多尺度融合：fuse4 输入 cat(diff4, backbone_e4) = 1024 → enc_dim
        self.fuse4 = nn.Conv2d(enc_dim * 2, enc_dim, 1, bias=False)
        # fuse3 输入 cat(f4, diffs[3]) = enc_dim + chs[3] → chs[2]
        self.fuse3 = nn.Conv2d(enc_dim + chs[3], chs[2], 3, padding=1, bias=False)
        # fuse2 输入 cat(f3, diffs[2]) = chs[2] + chs[2] → chs[1]
        self.fuse2 = nn.Conv2d(chs[2] + chs[2], chs[1], 3, padding=1, bias=False)
        # fuse1 输入 cat(f2, diffs[1]) = chs[1] + chs[1] → chs[0]
        self.fuse1 = nn.Conv2d(chs[1] + chs[1], chs[0], 3, padding=1, bias=False)

        self.decoder = nn.Sequential(
            nn.Conv2d(chs[0], 32, 3, padding=1, bias=False),
            nn.BatchNorm2d(32), nn.ReLU(inplace=True),
            nn.Upsample(scale_factor=2, mode='bilinear', align_corners=False),
            nn.Conv2d(32, 32, 3, padding=1, bias=False),
            nn.BatchNorm2d(32), nn.ReLU(inplace=True),
            nn.Upsample(scale_factor=2, mode='bilinear', align_corners=False),
            nn.Conv2d(32, output_nc, 3, padding=1),
        )

    def forward(self, x1, x2):
        f1 = _extract_backbone_features(self.backbone, x1)
        f2 = _extract_backbone_features(self.backbone, x2)

        # 瓶颈层 Transformer 在 e4 (最深特征) 上
        b = f1[4].shape[0]
        t1 = rearrange(f1[4], 'b c h w -> b (h w) c')
        t2 = rearrange(f2[4], 'b c h w -> b (h w) c')
        tokens = torch.cat([t1, t2], dim=1)
        if tokens.shape[1] <= self.pos_embed.shape[1]:
            pos = F.interpolate(
                self.pos_embed.unsqueeze(0).permute(0, 2, 1),
                size=tokens.shape[1], mode='linear', align_corners=False
            ).permute(0, 2, 1).squeeze(0)
            tokens = tokens + pos
        tokens = self.bottleneck_transformer(tokens)
        n = tokens.shape[1] // 2
        t1_out, t2_out = tokens[:, :n], tokens[:, n:]
        h = w = int(n ** 0.5)
        tf1 = rearrange(t1_out, 'b (h w) c -> b c h w', h=h, w=w)
        tf2 = rearrange(t2_out, 'b (h w) c -> b c h w', h=h, w=w)

        # 多尺度差分融合（自深到浅），differences 计算为 backbone 特征的差异
        diff_bk_4 = torch.abs(f1[4] - f2[4])
        diff_bk_3 = torch.abs(f1[3] - f2[3])
        diff_bk_2 = torch.abs(f1[2] - f2[2])
        diff_bk_1 = torch.abs(f1[1] - f2[1])

        diff4 = torch.abs(tf1 - tf2)
        f4 = self.fuse4(torch.cat([diff_bk_4, diff4], 1))

        f4_up = F.interpolate(f4, size=f1[3].shape[2:], mode='bilinear', align_corners=False)
        f3 = self.fuse3(torch.cat([f4_up, diff_bk_3], 1))

        f3_up = F.interpolate(f3, size=f1[2].shape[2:], mode='bilinear', align_corners=False)
        f2_out = self.fuse2(torch.cat([f3_up, diff_bk_2], 1))

        f2_up = F.interpolate(f2_out, size=f1[1].shape[2:], mode='bilinear', align_corners=False)
        f1_out = self.fuse1(torch.cat([f2_up, diff_bk_1], 1))

        return self.decoder(f1_out)


class BASE_Transformer(ResNet):
    """
    Resnet of 8 downsampling + BIT + bitemporal feature Differencing + a small CNN
    """
    def __init__(self, input_nc, output_nc, with_pos, resnet_stages_num=5,
                 token_len=4, token_trans=True,
                 enc_depth=1, dec_depth=1,
                 dim_head=64, decoder_dim_head=64,
                 tokenizer=True, if_upsample_2x=True,
                 pool_mode='max', pool_size=2,
                 backbone='resnet18',
                 decoder_softmax=True, with_decoder_pos=None,
                 with_decoder=True):
        super(BASE_Transformer, self).__init__(input_nc, output_nc,backbone=backbone,
                                             resnet_stages_num=resnet_stages_num,
                                               if_upsample_2x=if_upsample_2x,
                                               )
        self.token_len = token_len
        self.conv_a = nn.Conv2d(32, self.token_len, kernel_size=1,
                                padding=0, bias=False)
        self.tokenizer = tokenizer
        if not self.tokenizer:
            #  if not use tokenzier，then downsample the feature map into a certain size
            self.pooling_size = pool_size
            self.pool_mode = pool_mode
            self.token_len = self.pooling_size * self.pooling_size

        self.token_trans = token_trans
        self.with_decoder = with_decoder
        dim = 32
        mlp_dim = 2*dim

        self.with_pos = with_pos
        if with_pos == 'learned':
            self.pos_embedding = nn.Parameter(torch.randn(1, self.token_len*2, 32))
        decoder_pos_size = 256//4
        self.with_decoder_pos = with_decoder_pos
        if self.with_decoder_pos == 'learned':
            self.pos_embedding_decoder =nn.Parameter(torch.randn(1, 32,
                                                                 decoder_pos_size,
                                                                 decoder_pos_size))
        self.enc_depth = enc_depth
        self.dec_depth = dec_depth
        self.dim_head = dim_head
        self.decoder_dim_head = decoder_dim_head
        self.transformer = Transformer(dim=dim, depth=self.enc_depth, heads=8,
                                       dim_head=self.dim_head,
                                       mlp_dim=mlp_dim, dropout=0)
        self.transformer_decoder = TransformerDecoder(dim=dim, depth=self.dec_depth,
                            heads=8, dim_head=self.decoder_dim_head, mlp_dim=mlp_dim, dropout=0,
                                                      softmax=decoder_softmax)

    def _forward_semantic_tokens(self, x):
        b, c, h, w = x.shape
        spatial_attention = self.conv_a(x)
        spatial_attention = spatial_attention.view([b, self.token_len, -1]).contiguous()
        spatial_attention = torch.softmax(spatial_attention, dim=-1)
        x = x.view([b, c, -1]).contiguous()
        tokens = torch.einsum('bln,bcn->blc', spatial_attention, x)

        return tokens

    def _forward_reshape_tokens(self, x):
        # b,c,h,w = x.shape
        if self.pool_mode == 'max':
            x = F.adaptive_max_pool2d(x, [self.pooling_size, self.pooling_size])
        elif self.pool_mode == 'ave':
            x = F.adaptive_avg_pool2d(x, [self.pooling_size, self.pooling_size])
        else:
            x = x
        tokens = rearrange(x, 'b c h w -> b (h w) c')
        return tokens

    def _forward_transformer(self, x):
        if self.with_pos:
            x += self.pos_embedding
        x = self.transformer(x)
        return x

    def _forward_transformer_decoder(self, x, m):
        b, c, h, w = x.shape
        if self.with_decoder_pos == 'fix':
            x = x + self.pos_embedding_decoder
        elif self.with_decoder_pos == 'learned':
            x = x + self.pos_embedding_decoder
        x = rearrange(x, 'b c h w -> b (h w) c')
        x = self.transformer_decoder(x, m)
        x = rearrange(x, 'b (h w) c -> b c h w', h=h)
        return x

    def _forward_simple_decoder(self, x, m):
        b, c, h, w = x.shape
        b, l, c = m.shape
        m = m.expand([h,w,b,l,c])
        m = rearrange(m, 'h w b l c -> l b c h w')
        m = m.sum(0)
        x = x + m
        return x

    def forward(self, x1, x2):
        # forward backbone resnet
        x1 = self.forward_single(x1)
        x2 = self.forward_single(x2)

        #  forward tokenzier
        if self.tokenizer:
            token1 = self._forward_semantic_tokens(x1)
            token2 = self._forward_semantic_tokens(x2)
        else:
            token1 = self._forward_reshape_tokens(x1)
            token2 = self._forward_reshape_tokens(x2)
        # forward transformer encoder
        if self.token_trans:
            self.tokens_ = torch.cat([token1, token2], dim=1)
            self.tokens = self._forward_transformer(self.tokens_)
            token1, token2 = self.tokens.chunk(2, dim=1)
        # forward transformer decoder
        if self.with_decoder:
            x1 = self._forward_transformer_decoder(x1, token1)
            x2 = self._forward_transformer_decoder(x2, token2)
        else:
            x1 = self._forward_simple_decoder(x1, token1)
            x2 = self._forward_simple_decoder(x2, token2)
        # feature differencing
        x = torch.abs(x1 - x2)
        if not self.if_upsample_2x:
            x = self.upsamplex2(x)
        x = self.upsamplex4(x)
        # forward small cnn
        x = self.classifier(x)
        if self.output_sigmoid:
            x = self.sigmoid(x)
        return x


