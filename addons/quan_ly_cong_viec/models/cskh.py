# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class CskhTask(models.Model):
    _name = 'cskh_task'
    _description = 'Công việc CSKH'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # Archive support
    active = fields.Boolean(string="Hoạt động", default=True, tracking=True)

    task_id = fields.Char("Mã công việc", copy=False, readonly=True, index=True)
    name = fields.Char("Tên công việc", required=True, tracking=True)

    customer_id = fields.Many2one(
        'customer', string="Khách hàng",
        required=True, ondelete='cascade', index=True
    )

    phong_ban_id = fields.Many2one(
        'phong_ban',
        string="Bộ phận",
        default=lambda self: self.env['phong_ban'].search([('ten_phong', '=', 'Chăm sóc khách hàng')], limit=1),
        readonly=True,
        ondelete='restrict'
    )

    nhan_vien_id = fields.Many2one(
        'nhan_vien',
        string="Nhân viên chính phụ trách",
        ondelete='set null',
        tracking=True,
        domain="[('phong_ban_id.ten_phong', '=', 'Chăm sóc khách hàng')]"
    )

    team_member_ids = fields.Many2many(
        'nhan_vien',
        'cskh_task_nhan_vien_rel',
        'task_id',
        'nhan_vien_id',
        string="Thành viên tham gia",
        domain="[('phong_ban_id.ten_phong', '=', 'Chăm sóc khách hàng')]"
    )

    project_task_id = fields.Many2one(
        'project_task', string='Project Task', ondelete='cascade', copy=False,
        help='Mirrored project_task record for dashboard aggregation')

    source_model = fields.Selection([
        ('crm_interact', 'Tương tác khách hàng'),
        ('sale_order', 'Đơn hàng'),
        ('contract', 'Hợp đồng'),
        ('feedback', 'Phản hồi (Rating ≥ 3)'),
        ('note', 'Ghi chú khách hàng'),
    ], string="Nguồn", required=True, tracking=True)

    source_id = fields.Integer("ID Nguồn", help="ID của bản ghi tạo ra công việc")

    description = fields.Text("Mô tả")

    task_type = fields.Selection([
        ('goi_khach', 'Gọi khách'),
        ('email', 'Gửi email'),
        ('hop_khach', 'Họp khách hàng'),
        ('xu_ly_don', 'Xử lý đơn hàng'),
        ('giao_hang', 'Giao hàng'),
        ('support', 'Hỗ trợ kỹ thuật'),
        ('xu_ly_ghi_chu', 'Xử lý ghi chú'),
    ], string="Loại công việc", tracking=True)

    priority = fields.Selection([
        ('low', '🟢 Thấp'),
        ('medium', '🟡 Trung bình'),
        ('high', '🔴 Cao'),
        ('urgent', '🚨 Khẩn cấp'),
    ], default='medium', string="Mức độ ưu tiên", tracking=True, index=True)

    difficulty = fields.Selection([
        ('easy', '⭐ Dễ'),
        ('normal', '⭐⭐ Bình thường'),
        ('hard', '⭐⭐⭐ Khó'),
        ('very_hard', '⭐⭐⭐⭐ Rất khó'),
    ], default='normal', string="Mức độ khó", tracking=True)

    estimated_hours = fields.Float("Thời gian ước tính (giờ)", default=0.0, tracking=True)
    actual_hours = fields.Float("Thời gian thực tế (giờ)", default=0.0, tracking=True)
    progress = fields.Float("Tiến độ (%)", default=0.0, tracking=True)

    deadline = fields.Date("Hạn chót", tracking=True)
    actual_completion_date = fields.Date("Ngày hoàn thành thực tế", tracking=True)

    state = fields.Selection([
        ('todo', 'Chưa làm'),
        ('doing', 'Đang làm'),
        ('done', 'Hoàn thành'),
        ('cancel', 'Hủy'),
    ], default='todo', string="Trạng thái", tracking=True)

    is_overdue = fields.Boolean("Quá hạn", compute="_compute_is_overdue", store=True)

    days_remaining = fields.Integer(
        "Số ngày còn lại",
        compute="_compute_days_remaining",
        store=False
    )

    # -------------------------
    # COMPUTE
    # -------------------------

    @api.depends('deadline')
    def _compute_days_remaining(self):
        today = date.today()
        for rec in self:
            rec.days_remaining = (rec.deadline - today).days if rec.deadline else 0

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

    # -------------------------
    # SEQUENCE
    # -------------------------

    @api.model
    def create(self, vals):
        # Support both single dict and list-of-dicts creations
        seq_code = 'cskh_task'
        # ensure sequence exists to avoid returning a constant fallback
        if not self.env['ir.sequence'].search([('code', '=', seq_code)], limit=1):
            self.env['ir.sequence'].sudo().create({
                'name': 'CSKH Task Sequence',
                'code': seq_code,
                'prefix': 'CSKH',
                'padding': 5,
                'number_next': 1,
            })
        if isinstance(vals, list):
            for v in vals:
                if not v.get('task_id') or v.get('task_id') == 'New':
                    v['task_id'] = self.env['ir.sequence'].next_by_code(seq_code)
            records = super().create(vals)
        else:
            if not vals.get('task_id') or vals.get('task_id') == 'New':
                vals['task_id'] = self.env['ir.sequence'].next_by_code(seq_code)
            records = super().create(vals)

        # Mirror to project_task for dashboard aggregation
        # use context flag to avoid accidental recursion
        ptask_env = self.env['project_task'].with_context(from_cskh=True)
        to_write = []
        for rec in records:
            if rec.project_task_id:
                continue
            pvals = {
                'name': rec.name,
                'customer_id': rec.customer_id.id if rec.customer_id else False,
                'phong_ban_id': rec.phong_ban_id.id if rec.phong_ban_id else False,
                'nhan_vien_id': rec.nhan_vien_id.id if rec.nhan_vien_id else False,
                'description': rec.description or False,
                'task_type': rec.task_type or False,
                'priority': rec.priority or False,
                'difficulty': rec.difficulty or False,
                'estimated_hours': rec.estimated_hours or 0.0,
                'actual_hours': rec.actual_hours or 0.0,
                'progress': rec.progress or 0.0,
                'deadline': rec.deadline or False,
                'actual_completion_date': rec.actual_completion_date or False,
                'state': rec.state or 'todo',
            }
            p = ptask_env.create(pvals)
            to_write.append((rec.id, p.id))
        if to_write:
            for rid, pid in to_write:
                self.browse(rid).write({'project_task_id': pid})
        return records



    @api.model
    def create_from_interact(self, interacts):
        to_create = []
        for it in interacts:
            if not it.customer_id:
                continue
            name = it.crm_interact_name or it.crm_interact_id or f'Tương tác {it.id}'
            to_create.append({
                'name': name,
                'customer_id': it.customer_id.id,
                'source_model': 'crm_interact',
                'source_id': it.id,
                'description': f'Auto tạo từ tương tác: {name}',
            })
        if to_create:
            return self.create(to_create)
        return self.browse()

    @api.model
    def create_from_sale_order(self, orders):
        to_create = []
        for o in orders:
            if not o.customer_id:
                continue
            name = o.sale_order_name or o.sale_order_id or f'Đơn hàng {o.id}'
            to_create.append({
                'name': name,
                'customer_id': o.customer_id.id,
                'source_model': 'sale_order',
                'source_id': o.id,
                'description': f'Auto tạo từ đơn hàng: {name}',
            })
        if to_create:
            return self.create(to_create)
        return self.browse()

    @api.model
    def create_from_contract(self, contracts):
        to_create = []
        for c in contracts:
            if not c.customer_id:
                continue
            name = c.contract_name or c.contract_id or f'Hợp đồng {c.id}'
            to_create.append({
                'name': name,
                'customer_id': c.customer_id.id,
                'source_model': 'contract',
                'source_id': c.id,
                'description': f'Auto tạo từ hợp đồng: {name}',
            })
        if to_create:
            return self.create(to_create)
        return self.browse()

    @api.model
    def create_from_feedback(self, feedbacks):
        to_create = []
        for f in feedbacks:
            if not f.customer_id:
                continue
            # Skip if a CSKH task already exists for this feedback (prevent duplicates)
            try:
                existing = self.search([('source_model', '=', 'feedback'), ('source_id', '=', f.id)], limit=1)
                if existing:
                    continue
            except Exception:
                # If search fails for any reason, proceed to create (safer default)
                pass
            # Determine if feedback is negative (by sentiment label or rating)
            try:
                sent = (getattr(f, 'sentiment_label', None) or '').lower()
                is_negative = sent == 'negative' or str(getattr(f, 'rating', '') or '') in ('1', '2')
            except Exception:
                is_negative = False

            if is_negative:
                cust_name = getattr(f.customer_id, 'customer_name', None) or getattr(f.customer_id, 'name', None) or f.customer_id.id
                name = f'Xử lý phản hồi không hài lòng của khách hàng {cust_name}'
                desc = f'Auto tạo từ phản hồi (tiêu cực): {getattr(f, "feedback_name", None) or getattr(f, "feedback_id", None) or f"Phản hồi {f.id}"} (Đánh giá: {getattr(f, "rating", "")})'
                priority = 'high'
                # deadline within 24 hours
                try:
                    dl = date.today() + timedelta(days=1)
                except Exception:
                    dl = False
            else:
                name = f.feedback_name or f.feedback_id or f'Phản hồi {f.id}'
                desc = f'Auto tạo từ phản hồi: {name}'
                try:
                    priority = 'medium'
                    if (getattr(f, 'sentiment_label', None) or '').lower() == 'negative' or str(getattr(f, 'rating', '') or '') in ('1', '2'):
                        priority = 'high'
                except Exception:
                    priority = 'medium'
                dl = False

            to_create.append({
                'name': name,
                'customer_id': f.customer_id.id,
                'source_model': 'feedback',
                'source_id': f.id,
                'description': desc,
                'priority': priority,
                'deadline': dl or False,
            })
        if to_create:
            return self.create(to_create)
        return self.browse()

    @api.model
    def create_from_note(self, notes):
        to_create = []
        for n in notes:
            if not n.customer_id:
                continue
            name = n.note_name or n.note_id or f'Ghi chú {n.id}'
            to_create.append({
                'name': name,
                'customer_id': n.customer_id.id,
                'source_model': 'note',
                'source_id': n.id,
                'description': f'Auto tạo từ ghi chú: {name}',
            })
        if to_create:
            return self.create(to_create)
        return self.browse()

    # -------------------------
    # CONSTRAINTS
    # -------------------------

    @api.constrains('progress')
    def _check_progress(self):
        for rec in self:
            if rec.progress < 0 or rec.progress > 100:
                raise ValidationError("Tiến độ phải từ 0 đến 100%")

    @api.constrains('estimated_hours', 'actual_hours')
    def _check_hours(self):
        for rec in self:
            if rec.estimated_hours < 0:
                raise ValidationError("Thời gian ước tính không được âm!")
            if rec.actual_hours < 0:
                raise ValidationError("Thời gian thực tế không được âm!")

    # -------------------------
    # ACTIONS
    # -------------------------

    def action_start(self):
        self.write({'state': 'doing'})

    def action_done(self):
        for rec in self:
            if rec.state == 'cancel':
                raise ValidationError("Công việc đã hủy, không thể hoàn thành.")
            rec.write({
                'state': 'done',
                'progress': 100.0,
                'actual_completion_date': rec.actual_completion_date or fields.Date.today()
            })

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def write(self, vals):
        res = super().write(vals)
        # propagate updates to mirrored project_task
        if self._context.get('from_project_task'):
            return res
        propagate_fields = {}
        allowed = ['name', 'description', 'deadline', 'progress', 'state', 'nhan_vien_id', 'priority', 'task_type']
        for f in allowed:
            if f in vals:
                propagate_fields[f] = vals[f]
        if propagate_fields:
            for rec in self.filtered('project_task_id'):
                rec.project_task_id.with_context(from_cskh=True).write(propagate_fields)
        return res

    def unlink(self):
        # Remove mirrored project_task to keep dashboard showing only department tasks
        pts = self.mapped('project_task_id')
        # avoid recursion when unlink originates from project_task
        if pts and not self._context.get('from_project_task'):
            pts.with_context(from_cskh=True).unlink()
        return super().unlink()
