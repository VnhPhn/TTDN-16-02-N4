# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo import models, fields, api

class NhanVien(models.Model):
    _name = 'nhan_vien'
    _description = 'Bảng chứa thông tin nhân viên'
    _rec_name = 'ho_ten'

    ho_ten = fields.Char("Họ và tên", required=True)
    ngay_sinh = fields.Date("Ngày sinh")
    gioi_tinh = fields.Selection(
        selection=[
            ('nam', 'Nam'),
            ('nu', 'Nữ'),
            ('khac', 'Khác')
        ],
        string='Giới tính'
    )
    so_cmnd = fields.Char("Số CMND/CCCD", required=True)
    dia_chi = fields.Text("Địa chỉ")
    so_dien_thoai = fields.Char("Số điện thoại")
    email = fields.Char("Email")
    ngay_bat_dau_lam_viec = fields.Date("Ngày bắt đầu làm việc")
    
    # Quan hệ với phòng ban
    phong_ban_id = fields.Many2one(
        comodel_name='phong_ban',
        string='Phòng ban'
    )
    
    # Quan hệ với chức vụ hiện tại
    chuc_vu_id = fields.Many2one(
        comodel_name='chuc_vu',
        string='Chức vụ hiện tại'
    )
    
    # Lịch sử công tác
    lich_su_cong_tac_ids = fields.One2many(
        comodel_name='lich_su_cong_tac',
        inverse_name='nhan_vien_id',
        string='Lịch sử công tác'
    )
    
    # Chứng chỉ
    chung_chi_ids = fields.One2many(
        comodel_name='chung_chi',
        inverse_name='nhan_vien_id',
        string='Chứng chỉ'
    )
    
    # Hợp đồng
    hop_dong_ids = fields.One2many(
        comodel_name='hop_dong',
        inverse_name='nhan_vien_id',
        string='Hợp đồng'
    )

    # Lương cơ bản
    luong_co_ban = fields.Float(
        string="Lương cơ bản",
        default=0.0,
        help="Lương cơ bản hàng tháng"
    )
    
    so_a = fields.Integer("Số A")
    so_b = fields.Integer("Số B")
    tong_ab = fields.Integer("Tổng a + b", compute='_compute_tong_ab', store=True)

    @api.depends('so_a', 'so_b')
    def _compute_tong_ab(self):
        for record in self:
            record.tong_ab = record.so_a + record.so_b
    tuoi = fields.Integer("Tuổi", compute='_compute_tuoi', store=True)
    @api.depends('ngay_sinh')
    def _compute_tuoi(self):
        from datetime import date
        for record in self:
             if record.ngay_sinh:
                 year_now = date.today().year
                 record.tuoi = year_now - record.ngay_sinh.year
             else:
                 record.tuoi = 0
    @api.constrains('tuoi')
    def _check_tuoi(self):
        for record in self:
            if record.tuoi < 18:
                    raise ValidationError("Tuổi nhân viên phải lớn hơn hoặc bằng 18!")