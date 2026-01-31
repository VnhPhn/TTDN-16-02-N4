# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date


class MarketingTask(models.Model):
    _name = 'marketing_task'
    _description = 'Công việc Marketing'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    active = fields.Boolean(
    string="Hoạt động",
    default=True,
    tracking=True
)

    task_id = fields.Char("Mã công việc", copy=False, readonly=True, index=True)
    name = fields.Char("Tên công việc", required=True, tracking=True)

    customer_id = fields.Many2one(
        'customer', string="Khách hàng",
        ondelete='cascade', index=True
    )

    phong_ban_id = fields.Many2one(
        'phong_ban',
        string="Bộ phận",
        default=lambda self: self.env['phong_ban'].search([('ten_phong', '=', 'Marketing')], limit=1),
        readonly=True,
        ondelete='restrict'
    )

    nhan_vien_id = fields.Many2one(
        'nhan_vien',
        string="Nhân viên chính phụ trách",
        ondelete='set null',
        tracking=True,
        domain="[('phong_ban_id.ten_phong', '=', 'Marketing')]"
    )

    team_member_ids = fields.Many2many(
        'nhan_vien',
        'marketing_task_nhan_vien_rel',
        'task_id',
        'nhan_vien_id',
        string="Thành viên tham gia",
        domain="[('phong_ban_id.ten_phong', '=', 'Marketing')]"
    )

    project_task_id = fields.Many2one(
        'project_task', string='Project Task', ondelete='cascade', copy=False,
        help='Mirrored project_task record for dashboard aggregation')

    # Source
    source_model = fields.Selection([
        ('crm_interact', 'Tương tác khách'),
        ('feedback', 'Phân tích feedback'),
        ('marketing_campaign', 'Campaign'),
    ], string="Nguồn", required=True, tracking=True)

    source_id = fields.Integer("ID Nguồn")

    description = fields.Text("Mô tả")
    
    task_type = fields.Selection([
        ('tuong_tac_campaign', 'Tương tác cho campaign'),
        ('phan_tich_khach', 'Phân tích khách hàng'),
        ('thuc_hien_campaign', 'Thực hiện campaign'),
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

    @api.depends('deadline')
    def _compute_days_remaining(self):
        today = date.today()
        for rec in self:
            if rec.deadline:
                remaining = (rec.deadline - today).days
                rec.days_remaining = remaining
            else:
                rec.days_remaining = 0

    @api.model
    def create(self, vals):
        # Support single dict or list-of-dicts
        seq_code = 'marketing_task'
        if not self.env['ir.sequence'].search([('code', '=', seq_code)], limit=1):
            self.env['ir.sequence'].sudo().create({
                'name': 'Marketing Task Sequence',
                'code': seq_code,
                'prefix': 'MKT',
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

        # Mirror to project_task
        ptask_env = self.env['project_task'].with_context(from_marketing=True)
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
            if not getattr(it, 'customer_id', False):
                continue
            name = it.crm_interact_name if hasattr(it, 'crm_interact_name') else (getattr(it, 'crm_interact_id', False) or f'Interact {it.id}')
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
    def create_from_feedback(self, feedbacks):
        to_create = []
        for f in feedbacks:
            if not getattr(f, 'customer_id', False):
                continue
            name = f.feedback_name if hasattr(f, 'feedback_name') else (getattr(f, 'feedback_id', False) or f'Feedback {f.id}')
            to_create.append({
                'name': name,
                'customer_id': f.customer_id.id,
                'source_model': 'feedback',
                'source_id': f.id,
                'description': f'Auto tạo từ phản hồi: {name}',
            })
        if to_create:
            return self.create(to_create)
        return self.browse()

    @api.model
    def create_from_campaign(self, campaigns):
        to_create = []
        for c in campaigns:
            # campaign may not have customer; create generic task
            name = getattr(c, 'name', None) or getattr(c, 'marketing_campaign_id', None) or f'Campaign {c.id}'
            to_create.append({
                'name': name,
                'source_model': 'marketing_campaign',
                'source_id': c.id,
                'description': f'Auto tạo từ campaign: {name}',
            })
        if to_create:
            return self.create(to_create)
        return self.browse()

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

    def action_start(self):
        for rec in self:
            rec.state = 'doing'

    def action_done(self):
        for rec in self:
            if rec.state == 'cancel':
                raise ValidationError("Công việc đã hủy, không thể hoàn thành.")
            rec.state = 'done'
            rec.progress = 100.0
            if not rec.actual_completion_date:
                rec.actual_completion_date = fields.Date.today()

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancel'

    def write(self, vals):
        res = super().write(vals)
        if self._context.get('from_project_task'):
            return res
        propagate_fields = {}
        allowed = ['name', 'description', 'deadline', 'progress', 'state', 'nhan_vien_id', 'priority', 'task_type']
        for f in allowed:
            if f in vals:
                propagate_fields[f] = vals[f]
        if propagate_fields:
            for rec in self.filtered('project_task_id'):
                rec.project_task_id.with_context(from_marketing=True).write(propagate_fields)
        return res

    def unlink(self):
        pts = self.mapped('project_task_id')
        # avoid recursion when unlink originates from project_task
        if pts and not self._context.get('from_project_task'):
            pts.with_context(from_marketing=True).unlink()
        return super().unlink()
