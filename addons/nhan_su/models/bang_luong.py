# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime


class BangLuong(models.Model):
    _name = 'bang_luong'
    _description = 'Bảng lương'
    _rec_name = 'nhan_vien_id'

    nhan_vien_id = fields.Many2one('nhan_vien', string="Nhân viên", required=True)

    thang_nam = fields.Char(
        string="Tháng/Năm",
        required=True,
        help="Định dạng MM/YYYY (vd: 12/2025)"
    )

    # Tổng giờ làm trong tháng (từ chấm công)
    so_gio_lam = fields.Float(
        string="Số giờ làm",
        compute="_compute_so_gio_lam",
        store=True
    )

    # Số công/tháng
    so_cong = fields.Float(
        string="Số công/tháng",
        compute="_compute_so_cong",
        store=True,
        help="Số công = số giờ làm / 8"
    )

    # Lương cơ bản lấy từ nhân viên (bạn phải có field luong_co_ban trong nhan_vien)
    luong_co_ban = fields.Float(
        string="Lương cơ bản",
        related='nhan_vien_id.luong_co_ban',
        readonly=True
    )

    tien_thuong = fields.Float(string="Thưởng", default=0.0)
    tien_phat = fields.Float(string="Phạt", default=0.0)

    luong_nhan = fields.Float(
        string="Lương nhận",
        compute="_compute_luong_nhan",
        store=True
    )

    ghi_chu = fields.Text(string="Ghi chú")

    # ===== RULE =====
    GIO_CHUAN_NGAY = 8.0
    CONG_CHUAN_THANG = 26.0

    # -------------------------
    # Helpers
    # -------------------------
    def _get_month_year_range(self):
        """Trả về [start_date, end_date) cho MM/YYYY"""
        try:
            month, year = map(int, self.thang_nam.split('/'))
            start = datetime(year, month, 1)
            if month == 12:
                end = datetime(year + 1, 1, 1)
            else:
                end = datetime(year, month + 1, 1)
            return start.date(), end.date()
        except:
            return None, None

    # -------------------------
    # Compute tổng giờ làm từ chấm công
    # -------------------------
    @api.depends('nhan_vien_id', 'thang_nam')
    def _compute_so_gio_lam(self):
        for r in self:
            r.so_gio_lam = 0.0
            if not (r.nhan_vien_id and r.thang_nam):
                continue

            start_date, end_date = r._get_month_year_range()
            if not (start_date and end_date):
                continue

            cham_cong_recs = self.env['cham_cong'].search([
                ('nhan_vien_id', '=', r.nhan_vien_id.id),
                ('ngay_cham_cong', '>=', start_date),
                ('ngay_cham_cong', '<', end_date),
            ])

            r.so_gio_lam = sum(ch.so_gio_lam for ch in cham_cong_recs)

    # -------------------------
    # Compute số công
    # -------------------------
    @api.depends('so_gio_lam')
    def _compute_so_cong(self):
        for r in self:
            r.so_cong = round((r.so_gio_lam / self.GIO_CHUAN_NGAY), 2) if r.so_gio_lam else 0.0

    # -------------------------
    # Compute lương nhận
    # -------------------------
    @api.depends('so_cong', 'luong_co_ban', 'tien_thuong', 'tien_phat')
    def _compute_luong_nhan(self):
        for r in self:
            if r.luong_co_ban and r.so_cong:
                luong_1_cong = r.luong_co_ban / self.CONG_CHUAN_THANG
                r.luong_nhan = (luong_1_cong * r.so_cong) + r.tien_thuong - r.tien_phat
            else:
                r.luong_nhan = 0.0

    # -------------------------
    # Constrains
    # -------------------------
    @api.constrains('tien_thuong', 'tien_phat')
    def _check_tien_thuong_phat(self):
        for r in self:
            if r.tien_thuong < 0:
                raise ValidationError("Tiền thưởng không được âm!")
            if r.tien_phat < 0:
                raise ValidationError("Tiền phạt không được âm!")

    @api.constrains('thang_nam')
    def _check_thang_nam(self):
        import re
        for r in self:
            if not r.thang_nam:
                continue
            if not re.match(r'^\d{1,2}/\d{4}$', r.thang_nam):
                raise ValidationError("Định dạng tháng/năm không hợp lệ! Dùng MM/YYYY (vd: 12/2025)")
            month, year = map(int, r.thang_nam.split('/'))
            if month < 1 or month > 12:
                raise ValidationError("Tháng phải từ 1 đến 12!")

    # 1 nhân viên / 1 tháng chỉ 1 bảng lương
    _sql_constraints = [
        ('unique_nv_thang', 'unique(nhan_vien_id, thang_nam)',
         'Nhân viên đã có bảng lương cho tháng này!')
    ]
