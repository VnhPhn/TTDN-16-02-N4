# -*- coding: utf-8 -*-
from odoo import models, fields, api


class HopDong(models.Model):
    _name = 'hop_dong'
    _description = 'Bảng hợp đồng'
    _rec_name = 'so_hd'

    so_hd = fields.Char("Số hợp đồng", required=True, unique=True)
    ngay_ky = fields.Date("Ngày ký", required=True)
    ngay_het_han = fields.Date("Ngày hết hạn")
    loai_hop_dong = fields.Selection([
        ('thử việc', 'Thử việc'),
        ('xác định', 'Xác định'),
        ('không xác định', 'Không xác định'),
        ('full time', 'Full time'),
        ('part time', 'Part time'),
    ], string='Loại hợp đồng', required=True)
    
    mo_ta = fields.Text("Mô tả")
    trang_thai = fields.Selection([
        ('nháp', 'Nháp'),
        ('có hiệu lực', 'Có hiệu lực'),
        ('hết hạn', 'Hết hạn'),
        ('chấm dứt', 'Chấm dứt'),
    ], string='Trạng thái', default='nháp')

    # Quan hệ với nhân viên
    nhan_vien_id = fields.Many2one(
        comodel_name='nhan_vien',
        string='Nhân viên',
        required=True
    )
    
    phong_ban_id = fields.Many2one(
        comodel_name='phong_ban',
        string='Phòng ban',
        readonly=True
    )
    
    ghi_chu = fields.Text("Ghi chú")
