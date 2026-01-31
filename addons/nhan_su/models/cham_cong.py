# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, time


class ChamCong(models.Model):
    _name = 'cham_cong'
    _description = 'Chấm công nhân viên'
    _rec_name = 'ngay_cham_cong'
    _order = 'ngay_cham_cong desc'

    nhan_vien_id = fields.Many2one('nhan_vien', string="Nhân viên", required=True)

    ngay_cham_cong = fields.Date(
        string="Ngày chấm công",
        required=True,
        default=fields.Date.today
    )

    gio_vao = fields.Char(string="Giờ vào", default='08:30:00', help="Định dạng HH:MM:SS")
    gio_ra = fields.Char(string="Giờ ra", default='17:30:00', help="Định dạng HH:MM:SS")

    gio_nghi_bat_dau = fields.Char(string="Giờ bắt đầu nghỉ", default='12:30:00', help="Định dạng HH:MM:SS")
    gio_nghi_ket_thuc = fields.Char(string="Giờ kết thúc nghỉ", default='13:30:00', help="Định dạng HH:MM:SS")

    # ====== KẾT QUẢ ======
    so_gio_lam = fields.Float(string="Số giờ làm", compute="_compute_so_gio_lam", store=True)

    di_muon = fields.Boolean(string="Đi muộn", compute="_compute_muon_som", store=True)
    ve_som = fields.Boolean(string="Về sớm", compute="_compute_muon_som", store=True)
    so_phut_di_muon = fields.Integer(string="Số phút đi muộn", compute="_compute_muon_som", store=True)
    so_phut_ve_som = fields.Integer(string="Số phút về sớm", compute="_compute_muon_som", store=True)

    trang_thai = fields.Selection([
        ('co_mat', 'Có mặt'),
        ('di_muon', 'Đi muộn'),
        ('ve_som', 'Về sớm'),
        ('di_muon_ve_som', 'Đi muộn & Về sớm'),
    ], string="Trạng thái", compute="_compute_trang_thai", store=True, default='co_mat')

    ghi_chu = fields.Text(string="Ghi chú")

    # ===== RULE =====
    GIO_VAO_CHUAN = time(8, 30, 0)
    GIO_RA_CHUAN = time(17, 30, 0)

    # -------------------------
    # Helpers
    # -------------------------
    def _parse_time(self, s):
        return datetime.strptime(s, '%H:%M:%S').time()

    def _dt(self, d, t):
        return datetime.combine(d, t)

    # -------------------------
    # Compute số giờ làm (trừ nghỉ trưa theo overlap)
    # -------------------------
    @api.depends('ngay_cham_cong', 'gio_vao', 'gio_ra', 'gio_nghi_bat_dau', 'gio_nghi_ket_thuc')
    def _compute_so_gio_lam(self):
        for r in self:
            r.so_gio_lam = 0.0
            if not (r.ngay_cham_cong and r.gio_vao and r.gio_ra and r.gio_nghi_bat_dau and r.gio_nghi_ket_thuc):
                continue
            try:
                t_in = r._parse_time(r.gio_vao)
                t_out = r._parse_time(r.gio_ra)
                t_break_s = r._parse_time(r.gio_nghi_bat_dau)
                t_break_e = r._parse_time(r.gio_nghi_ket_thuc)

                dt_in = r._dt(r.ngay_cham_cong, t_in)
                dt_out = r._dt(r.ngay_cham_cong, t_out)
                dt_break_s = r._dt(r.ngay_cham_cong, t_break_s)
                dt_break_e = r._dt(r.ngay_cham_cong, t_break_e)

                if dt_out <= dt_in:
                    r.so_gio_lam = 0.0
                    continue

                total_sec = (dt_out - dt_in).total_seconds()

                # overlap với nghỉ trưa
                overlap_start = max(dt_in, dt_break_s)
                overlap_end = min(dt_out, dt_break_e)
                overlap_sec = (overlap_end - overlap_start).total_seconds() if overlap_end > overlap_start else 0

                work_sec = max(total_sec - overlap_sec, 0)
                r.so_gio_lam = work_sec / 3600.0
            except:
                r.so_gio_lam = 0.0

    # -------------------------
    # Compute đi muộn / về sớm + số phút
    # -------------------------
    @api.depends('ngay_cham_cong', 'gio_vao', 'gio_ra')
    def _compute_muon_som(self):
        for r in self:
            r.di_muon = False
            r.ve_som = False
            r.so_phut_di_muon = 0
            r.so_phut_ve_som = 0

            if not (r.ngay_cham_cong and r.gio_vao and r.gio_ra):
                continue

            try:
                t_in = r._parse_time(r.gio_vao)
                t_out = r._parse_time(r.gio_ra)

                # đi muộn
                if t_in > self.GIO_VAO_CHUAN:
                    r.di_muon = True
                    dt_std_in = r._dt(r.ngay_cham_cong, self.GIO_VAO_CHUAN)
                    dt_in = r._dt(r.ngay_cham_cong, t_in)
                    r.so_phut_di_muon = int((dt_in - dt_std_in).total_seconds() // 60)

                # về sớm
                if t_out < self.GIO_RA_CHUAN:
                    r.ve_som = True
                    dt_std_out = r._dt(r.ngay_cham_cong, self.GIO_RA_CHUAN)
                    dt_out = r._dt(r.ngay_cham_cong, t_out)
                    r.so_phut_ve_som = int((dt_std_out - dt_out).total_seconds() // 60)

            except:
                # giữ mặc định
                pass

    # -------------------------
    # Compute trạng thái từ 2 cờ
    # -------------------------
    @api.depends('di_muon', 've_som')
    def _compute_trang_thai(self):
        for r in self:
            if r.di_muon and r.ve_som:
                r.trang_thai = 'di_muon_ve_som'
            elif r.di_muon:
                r.trang_thai = 'di_muon'
            elif r.ve_som:
                r.trang_thai = 've_som'
            else:
                r.trang_thai = 'co_mat'

    # -------------------------
    # Constrains
    # -------------------------
    @api.constrains('gio_vao', 'gio_ra')
    def _check_gio_vao_ra(self):
        for r in self:
            if not (r.gio_vao and r.gio_ra):
                continue
            try:
                t_in = r._parse_time(r.gio_vao)
                t_out = r._parse_time(r.gio_ra)
                if t_out < t_in:
                    raise ValidationError("Giờ ra phải lớn hơn hoặc bằng giờ vào!")
            except ValidationError:
                raise
            except:
                raise ValidationError("Định dạng giờ không hợp lệ! Vui lòng dùng HH:MM:SS")

    @api.constrains('gio_nghi_bat_dau', 'gio_nghi_ket_thuc')
    def _check_gio_nghi(self):
        for r in self:
            if not (r.gio_nghi_bat_dau and r.gio_nghi_ket_thuc):
                continue
            try:
                t_s = r._parse_time(r.gio_nghi_bat_dau)
                t_e = r._parse_time(r.gio_nghi_ket_thuc)
                if t_e <= t_s:
                    raise ValidationError("Giờ kết thúc nghỉ phải lớn hơn giờ bắt đầu nghỉ!")
            except ValidationError:
                raise
            except:
                raise ValidationError("Định dạng giờ nghỉ không hợp lệ! Vui lòng dùng HH:MM:SS")

    _sql_constraints = [
        ('unique_nv_ngay', 'unique(nhan_vien_id, ngay_cham_cong)',
         'Mỗi nhân viên chỉ được chấm công 1 lần trong 1 ngày!')
    ]
