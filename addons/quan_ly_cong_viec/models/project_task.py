# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class ProjectTask(models.Model):
    _name = 'project_task'
    _description = 'Bảng chứa thông tin nhiệm vụ'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    project_task_id = fields.Char("Mã nhiệm vụ", copy=False, readonly=True, index=True)
    name = fields.Char("Tên nhiệm vụ", required=True, tracking=True)

    customer_id = fields.Many2one(
        'customer', string="Khách hàng",
        required=True, ondelete='cascade', index=True
    )

    # ✅ THÊM: Bộ phận xử lý (CSKH/Kỹ thuật/Marketing/Sales/Sản xuất)
    phong_ban_id = fields.Many2one(
        'phong_ban',
        string="Bộ phận xử lý",
        required=True,
        ondelete='restrict',
        tracking=True,
        index=True
    )

    # ✅ SỬA: Nhân viên phụ trách + lọc theo bộ phận
    nhan_vien_id = fields.Many2one(
        'nhan_vien',
        string="Nhân viên chính phụ trách",
        ondelete='set null',
        tracking=True,
        domain="[('phong_ban_id','=',phong_ban_id)]"
    )

    # ✅ THÊM: Phân công nhiều người (team members)
    team_member_ids = fields.Many2many(
        'nhan_vien',
        'project_task_nhan_vien_rel',
        'task_id',
        'nhan_vien_id',
        string="Thành viên tham gia",
        domain="[('phong_ban_id','=',phong_ban_id)]",
        help="Những nhân viên khác tham gia vào công việc này"
    )

    description = fields.Text("Mô tả")

    # dynamic selection: union of department-specific types
    def _get_task_type_options(self):
        return [
            ('goi_khach', 'Gọi khách'),
            ('email', 'Gửi email'),
            ('hop_khach', 'Họp khách'),
            ('xu_ly_don', 'Xử lý đơn hàng'),
            ('giao_hang', 'Giao hàng'),
            ('support', 'Hỗ trợ kỹ thuật'),
            ('xu_ly_ghi_chu', 'Xử lý ghi chú'),
            ('follow_up_lead', 'Follow-up Lead'),
            ('dam_phan', 'Đàm phán'),
            ('ky_ket', 'Ký kết'),
            ('tuong_tac_campaign', 'Tương tác Campaign'),
            ('phan_tich_khach', 'Phân tích khách hàng'),
            ('thuc_hien_campaign', 'Thực hiện campaign'),
            ('fix_issue', 'Sửa chữa vấn đề'),
            ('support_tech', 'Hỗ trợ kỹ thuật (Kỹ thuật)'),
            ('investigation', 'Điều tra/Phân tích'),
            ('phan_tich', 'Phân tích'),
            ('khac', 'Khác'),
        ]

    task_type = fields.Selection(selection=_get_task_type_options, string='Loại công việc', tracking=True)

    # ✅ THÊM: Phân loại/Dự án (Project/Category)
    project_category_id = fields.Many2one(
        'project.category',
        string="Phân loại công việc",
        ondelete='set null',
        tracking=True,
        help="Dự án hoặc danh mục công việc"
    )

    # ✅ THÊM: Hệ thống ưu tiên
    priority = fields.Selection([
        ('low', '🟢 Thấp'),
        ('medium', '🟡 Trung bình'),
        ('high', '🔴 Cao'),
        ('urgent', '🚨 Khẩn cấp'),
    ], default='medium', string="Mức độ ưu tiên", tracking=True, index=True)

    # ✅ THÊM: Mức độ khó
    difficulty = fields.Selection([
        ('easy', '⭐ Dễ'),
        ('normal', '⭐⭐ Bình thường'),
        ('hard', '⭐⭐⭐ Khó'),
        ('very_hard', '⭐⭐⭐⭐ Rất khó'),
    ], default='normal', string="Mức độ khó", tracking=True)

    # ✅ THÊM: Thời gian ước tính (hours)
    estimated_hours = fields.Float(
        "Thời gian ước tính (giờ)",
        default=0.0,
        tracking=True,
        help="Số giờ dự kiến để hoàn thành công việc"
    )

    # ✅ THÊM: Thời gian thực tế (hours)
    actual_hours = fields.Float(
        "Thời gian thực tế (giờ)",
        default=0.0,
        tracking=True,
        help="Số giờ thực tế đã sử dụng"
    )

    # ✅ THÊM: Tiến độ (%)
    progress = fields.Float(
        "Tiến độ (%)",
        default=0.0,
        tracking=True,
        help="Phần trăm hoàn thành công việc (0-100)"
    )

    deadline = fields.Date("Hạn chót", tracking=True)
    actual_completion_date = fields.Date("Ngày hoàn thành thực tế", tracking=True)

    state = fields.Selection([
        ('todo', 'Chưa làm'),
        ('doing', 'Đang làm'),
        ('done', 'Hoàn thành'),
        ('cancel', 'Hủy'),
    ], default='todo', string="Trạng thái", tracking=True)

    is_overdue = fields.Boolean("Quá hạn", compute="_compute_is_overdue", store=True)

    # ✅ THÊM: Tính toán số ngày còn lại
    days_remaining = fields.Integer(
        "Số ngày còn lại",
        compute="_compute_days_remaining",
        store=False,
        help="Số ngày còn lại đến deadline"
    )

    @api.depends('deadline')
    def _compute_days_remaining(self):
        today = date.today()
        for rec in self:
            if rec.deadline:
                remaining = (rec.deadline - today).days
                rec.days_remaining = remaining
            else:
                rec.days_remaining = 0

    # ✅ THÊM: Auto-generate mã nhiệm vụ
    @api.model
    def create(self, vals):
        if not vals.get('project_task_id') or vals.get('project_task_id') == 'New':
            vals['project_task_id'] = self.env['ir.sequence'].next_by_code('project_task') or 'TASK000001'
        return super().create(vals)

    @api.depends('deadline', 'actual_completion_date', 'state')
    def _compute_is_overdue(self):
        today = date.today()
        for rec in self:
            if rec.state == 'done' and rec.actual_completion_date and rec.deadline:
                rec.is_overdue = rec.actual_completion_date > rec.deadline
            elif rec.state != 'done' and rec.deadline:
                rec.is_overdue = today > rec.deadline
            else:
                rec.is_overdue = False

    # ✅ THÊM: đổi bộ phận thì reset NV + auto gán nếu chỉ có 1 NV trong bộ phận đó
    @api.onchange('phong_ban_id')
    def _onchange_phong_ban_id(self):
        for rec in self:
            rec.nhan_vien_id = False
            if rec.phong_ban_id:
                employees = self.env['nhan_vien'].search(
                    [('phong_ban_id', '=', rec.phong_ban_id.id)],
                    limit=2
                )
                if len(employees) == 1:
                    rec.nhan_vien_id = employees.id

    # ✅ THÊM: chặn chọn sai bộ phận
    @api.constrains('phong_ban_id', 'nhan_vien_id')
    def _check_employee_department(self):
        for rec in self:
            if rec.nhan_vien_id and rec.phong_ban_id:
                if rec.nhan_vien_id.phong_ban_id.id != rec.phong_ban_id.id:
                    raise ValidationError("Nhân viên được chọn không thuộc bộ phận xử lý của nhiệm vụ!")

    # ✅ THÊM: Validation tiến độ (0-100)
    @api.constrains('progress')
    def _check_progress(self):
        for rec in self:
            if rec.progress < 0 or rec.progress > 100:
                raise ValidationError("Tiến độ phải từ 0 đến 100%")

    # ✅ THÊM: Validation thời gian ước tính > 0
    @api.constrains('estimated_hours', 'actual_hours')
    def _check_hours(self):
        for rec in self:
            if rec.estimated_hours < 0:
                raise ValidationError("Thời gian ước tính không được âm!")
            if rec.actual_hours < 0:
                raise ValidationError("Thời gian thực tế không được âm!")

    def action_start(self):
        for rec in self:
            rec.state = 'doing'

    def action_done(self):
        for rec in self:
            if rec.state == 'cancel':
                raise ValidationError("Công việc đã hủy, không thể hoàn thành.")
            rec.state = 'done'
            rec.progress = 100.0  # ✅ TỰ ĐỘNG đặt tiến độ = 100%
            if not rec.actual_completion_date:
                rec.actual_completion_date = fields.Date.today()

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'

    def write(self, vals):
        # If state is set to 'done' via UI (kanban drag), ensure project_task itself gets progress and completion date
        if not (self._context.get('from_cskh') or self._context.get('from_sales') or self._context.get('from_marketing') or self._context.get('from_ky_thuat') or self._context.get('from_project_task')):
            if vals.get('state') == 'done':
                vals.setdefault('progress', 100.0)
                vals.setdefault('actual_completion_date', fields.Date.today())

        res = super().write(vals)
        # avoid propagating when the change originates from a department task
        if self._context.get('from_cskh') or self._context.get('from_sales') or self._context.get('from_marketing') or self._context.get('from_ky_thuat') or self._context.get('from_project_task'):
            return res

        propagate_fields = {}
        allowed = ['name', 'description', 'deadline', 'progress', 'state', 'nhan_vien_id', 'priority', 'actual_completion_date', 'estimated_hours', 'actual_hours', 'difficulty', 'task_type']
        for f in allowed:
            if f in vals:
                propagate_fields[f] = vals[f]

        if propagate_fields:
            # if state was changed to 'done', ensure progress + completion date propagate as well
            if propagate_fields.get('state') == 'done':
                # prefer provided actual_completion_date, otherwise use today
                propagate_fields.setdefault('progress', 100.0)
                propagate_fields.setdefault('actual_completion_date', fields.Date.today())

            dept_models = ['cskh_task', 'sales_task', 'marketing_task', 'ky_thuat_task']
            for rec in self:
                for m in dept_models:
                    tasks = self.env[m].search([('project_task_id', '=', rec.id)])
                    if tasks:
                        # mark origin to avoid recursion back to project_task
                        tasks.with_context(from_project_task=True).write(propagate_fields)
        return res

    def unlink(self):
        # when a dashboard/project_task is removed, remove mirrored department tasks
        # Use context to avoid recursion back to project_task.unlink
        dept_models = ['cskh_task', 'sales_task', 'marketing_task', 'ky_thuat_task']
        for rec in self:
            for m in dept_models:
                try:
                    tasks = self.env[m].search([('project_task_id', '=', rec.id)])
                    if tasks:
                        tasks.with_context(from_project_task=True).unlink()
                except Exception:
                    # fallback: clear the link if unlink fails for safety
                    try:
                        tasks.with_context(from_project_task=True).write({'project_task_id': False})
                    except Exception:
                        pass
        return super().unlink()

