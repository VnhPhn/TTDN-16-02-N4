import re
from odoo import models, fields, api, tools
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, date
import logging

_logger = logging.getLogger(__name__)

# Tier thresholds (currency = VND)
# Use these constants to keep tier logic centralized and clear.
TIER_AMOUNTS = {
    'platinum': 500_000_000,
    'gold': 200_000_000,
    'silver': 50_000_000,
}

TIER_ORDER_COUNTS = {
    'platinum': 50,
    'gold': 20,
    'silver': 5,
}

class Customer(models.Model):
    _name = 'customer'
    _description = 'Bảng chứa thông tin khách hàng'
    _sql_constraints = [
        ('customer_id_unique', 'unique(customer_id)', 'Mã khách hàng phải là duy nhất!'),
    ]
    near_birthday = fields.Boolean(
    "Gần tới sinh nhật",
    compute="_compute_near_birthday",
    store=False,
    help="Kiểm tra xem có gần tới sinh nhật khách hàng (trong vòng 7 ngày) hay không"
    )

    # Các trường cơ bản
    customer_id = fields.Char("Mã khách hàng", required=True, index=True, copy=False, default="New")
    customer_name = fields.Char("Tên khách hàng")
    email = fields.Char("Email")
    phone = fields.Char("Số điện thoại")
    address = fields.Char("Địa chỉ")
    gender = fields.Selection([
        ('male', 'Nam'),
        ('female', 'Nữ'),
        ('other', 'Khác')
    ], string="Giới tính")
    date_of_birth = fields.Date("Ngày sinh")
    age = fields.Integer("Tuổi", compute="_compute_age", store=True)
    income_level = fields.Selection([
        ('0-20tr', '0-20 triệu/tháng'),
        ('20-50tr', '20-50 triệu/tháng'),
        ('50-70tr', '50-70 triệu/tháng'),
        ('70-100tr', '70-100 triệu/tháng'),
        ('100tr+', '100 triệu trở lên')
    ], string="Mức thu nhập")
    image = fields.Binary("Ảnh", attachment=True)
    company_name = fields.Char("Tên công ty")
    tax_code = fields.Char("Mã số thuế")
    customer_type = fields.Selection([
        ('individual', 'Cá nhân'),
        ('company', 'Công ty')
    ], string="Loại khách hàng", default="individual")
    active = fields.Boolean("Active", default=True)
    customer_status = fields.Selection([
        ('new', 'Mới'),
        ('active', 'Đang hoạt động'),
        ('inactive', 'Không hoạt động')
    ], string="Trạng thái", default="new")

    # Trường liên kết với các model khác
    sale_order_ids = fields.One2many('sale_order', inverse_name='customer_id', string="Đơn hàng")
    interact_ids = fields.One2many('crm_interact', inverse_name='customer_id', string="Tương tác")
    contract_ids = fields.One2many('contract', inverse_name='customer_id', string="Hợp đồng")
    lead_ids = fields.One2many('crm_lead', inverse_name='customer_id', string="Cơ hội")
    feedback_ids = fields.One2many('feedback', inverse_name='customer_id', string="Phản hồi")
    note_ids = fields.One2many('note', inverse_name='customer_id', string="Ghi chú")

    # Trường tính toán (computed fields)
    total_contracts = fields.Integer("Tổng số hợp đồng", compute="_compute_total_contracts", store=True)
    total_interactions = fields.Integer("Tổng số tương tác", compute="_compute_total_interactions", store=True)
    total_sale_orders = fields.Integer("Tổng số đơn hàng", compute="_compute_total_sale_orders", store=True)
    total_amount = fields.Float("Tổng số tiền đơn hàng", compute="_compute_total_amount", store=True)
    # Loyalty and tier
    loyalty_points = fields.Integer("Điểm thành viên", default=0, store=True)
    customer_tier = fields.Selection([
        ('bronze', 'Đồng'),
        ('silver', 'Bạc'),
        ('gold', 'Vàng'),
        ('platinum', 'Bạch kim'),
    ], string="Hạng khách hàng", compute="_compute_customer_tier", store=True)
    recent_interactions = fields.Integer("Số tương tác trong tháng", compute="_compute_recent_interactions", store=True)

    age_group = fields.Selection([
        ('0-20', '0-20 tuổi'),
        ('20-30', '20-30 tuổi'),
        ('30-40', '30-40 tuổi'),
        ('40-50', '40-50 tuổi'),
        ('50+', 'Trên 50 tuổi')
    ], string="Nhóm độ tuổi", compute="_compute_age_group", store=True)

    # Trường mới: Nhóm số đơn hàng
    sale_order_group = fields.Selection([
        ('0', '0 đơn hàng'),
        ('1-5', '1-5 đơn hàng'),
        ('5-10', '5-10 đơn hàng'),
        ('10+', 'Trên 10 đơn hàng')
    ], string="Nhóm số đơn hàng", compute="_compute_sale_order_group", store=True)

    @api.depends('age')
    def _compute_age_group(self):
        for record in self:
            age = record.age
            if age <= 20:
                record.age_group = '0-20'
            elif 20 < age <= 30:
                record.age_group = '20-30'
            elif 30 < age <= 40:
                record.age_group = '30-40'
            elif 40 < age <= 50:
                record.age_group = '40-50'
            else:
                record.age_group = '50+'

    @api.depends('total_sale_orders')
    def _compute_sale_order_group(self):
        for record in self:
            orders = record.total_sale_orders
            if orders == 0:
                record.sale_order_group = '0'
            elif 1 <= orders <= 5:
                record.sale_order_group = '1-5'
            elif 5 < orders <= 10:
                record.sale_order_group = '5-10'
            else:
                record.sale_order_group = '10+'

    # Ràng buộc cho email
    @api.constrains('email')
    def _check_email(self):
        email_pattern = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        for record in self:
            if record.email and not re.match(email_pattern, record.email):
                raise ValidationError("Email không hợp lệ: %s" % record.email)
            
    @api.constrains('phone')
    def _check_phone(self):
        phone_pattern = r'^(\+84|0)[1-9]\d{8,9}$'  # Ví dụ: +84981234567 hoặc 0981234567
        for record in self:
            if record.phone and not re.match(phone_pattern, record.phone):
                raise ValidationError("Số điện thoại không hợp lệ! Ví dụ hợp lệ: 0987654321 hoặc +84987654321")
            
    # Tính toán tổng số hợp đồng
    @api.depends('contract_ids')
    def _compute_total_contracts(self):
        for record in self:
            record.total_contracts = len(record.contract_ids)

    # Tính toán tổng số tương tác
    @api.depends('interact_ids')
    def _compute_total_interactions(self):
        for record in self:
            record.total_interactions = len(record.interact_ids)

    # Tính toán tổng số đơn hàng
    @api.depends('sale_order_ids')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.sale_order_ids.mapped('amount_total')) or 0.0

    @api.depends('sale_order_ids')
    def _compute_total_sale_orders(self):
        for record in self:
            record.total_sale_orders = len(record.sale_order_ids)

    @api.depends('total_amount', 'total_sale_orders', 'contract_ids', 'lead_ids', 'contract_ids', 'interact_ids')
    def _compute_customer_tier(self):
        """Compute customer tier based on thresholds.

        Rules (default): thresholds are defined in the module-level
        dictionaries `TIER_AMOUNTS` (VND) and `TIER_ORDER_COUNTS`.
        """
        for record in self:
            amt = float(record.total_amount or 0.0)
            orders = int(record.total_sale_orders or 0)

            if amt >= TIER_AMOUNTS['platinum'] or orders >= TIER_ORDER_COUNTS['platinum']:
                record.customer_tier = 'platinum'
            elif amt >= TIER_AMOUNTS['gold'] or orders >= TIER_ORDER_COUNTS['gold']:
                record.customer_tier = 'gold'
            elif amt >= TIER_AMOUNTS['silver'] or orders >= TIER_ORDER_COUNTS['silver']:
                record.customer_tier = 'silver'
            else:
                record.customer_tier = 'bronze'

    @api.model
    def recompute_loyalty_points(self, rate=1000):
        """Recompute loyalty_points from full sale_order and interact history.

        - `rate`: currency units per 1 point (default 1000).
        Points from interactions use a fixed map.
        This ensures points reflect full history, not incremental writes.
        """
        points_map = {
            'meeting': 10,
            'call': 2,
            'email': 1,
        }
        customers = self
        if not customers:
            customers = self.search([])
        for c in customers:
            try:
                total_points = 0
                # points from sale orders
                for so in c.sale_order_ids:
                    try:
                        total_points += int((so.amount_total or 0.0) / rate)
                    except Exception:
                        continue
                # points from interactions
                for intr in c.interact_ids:
                    try:
                        total_points += points_map.get(intr.interaction_type, 0)
                    except Exception:
                        continue
                if c.loyalty_points != total_points:
                    c.write({'loyalty_points': total_points})
            except Exception:
                _logger.exception('Failed to recompute loyalty points for customer %s', c.id)

    def add_loyalty_points(self, points, reason=None, user_id=None):
        """Add loyalty points to customer(s).

        - `points` should be an integer (can be negative to deduct).
        - `reason` is an optional string stored only in logs.
        """
        try:
            pts = int(points)
        except Exception:
            _logger.warning('Invalid points value passed to add_loyalty_points: %s', points)
            return
        for rec in self:
            try:
                current = int(rec.loyalty_points or 0)
                new = current + pts
                if new < 0:
                    new = 0
                rec.write({'loyalty_points': new})
                _logger.info('Customer %s: loyalty points changed %s -> %s (reason=%s, user=%s)', rec.id, current, new, reason, user_id)
            except Exception:
                _logger.exception('Failed to add loyalty points for customer %s', rec.id)

    @api.constrains('date_of_birth')
    def _check_date_of_birth(self):
        today = fields.Date.today()
        for record in self:
            if record.date_of_birth:
            # Kiểm tra ngày trong tương lai
                if record.date_of_birth > today:
                    raise ValidationError("Ngày sinh không được vượt quá ngày hiện tại!")
            # Kiểm tra ngày hợp lệ
                try:
                    date(record.date_of_birth.year, record.date_of_birth.month, record.date_of_birth.day)
                except ValueError:
                    raise ValidationError("Ngày sinh không hợp lệ!")

    @api.depends('date_of_birth')
    def _compute_age(self):
        today = fields.Date.today()
        for record in self:
            record.age = 0
            if record.date_of_birth:
                record.age = (today - record.date_of_birth).days // 365

    @api.depends('date_of_birth')
    def _compute_near_birthday(self):
        today = fields.Date.today()
        for record in self:
            if record.date_of_birth:
                birthday = record.date_of_birth.replace(year=today.year)
                # Nếu sinh nhật đã qua trong năm nay, chuyển sang năm sau
                if birthday < today:
                    birthday = birthday.replace(year=today.year + 1)
                days_until_birthday = (birthday - today).days
                record.near_birthday = 0 <= days_until_birthday <= 7
            else:
                record.near_birthday = False

    @api.constrains('customer_name', 'email', 'phone', 'customer_type', 'company_name', 'tax_code')
    def _check_required_fields(self):
        for record in self:
            # Kiểm tra các trường bắt buộc cố định
            if not record.customer_name:
                raise ValidationError("Vui lòng nhập Tên khách hàng!")
            if not record.email:
                raise ValidationError("Vui lòng nhập Email!")
            if not record.phone:
                raise ValidationError("Vui lòng nhập Số điện thoại!")
            
            # Kiểm tra các trường bắt buộc động (khi customer_type là company)
            if record.customer_type == 'company':
                if not record.company_name:
                    raise ValidationError("Vui lòng nhập Tên công ty!")
                if not record.tax_code:
                    raise ValidationError("Vui lòng nhập Mã số thuế!")
                
    # Đặt tên hiển thị cho bản ghi
    def name_get(self):
        result = []
        for record in self:
            if record.customer_type == 'company':
                name = f"[{record.customer_id}] {record.customer_name} (Công ty)"
            else:
                name = f"[{record.customer_id}] {record.customer_name}"
            result.append((record.id, name))
        return result

    @api.model
    def create(self, vals):
        if vals.get('customer_id', 'New') == 'New':
            sequence = self.env['ir.sequence'].search([('code', '=', 'customer.id')], limit=1)
        # Lấy mã lớn nhất hiện có
            max_record = self.search([], order='customer_id desc', limit=1)
            max_code = max_record.customer_id if max_record else 'KH00000'
        # Kiểm tra và lấy số tiếp theo
            try:
                next_num = int(max_code.replace('KH', '')) + 1
            except ValueError:
                next_num = 1  # Bắt đầu từ 1 nếu không có mã hợp lệ
            sequence.write({'number_next': next_num})
            vals['customer_id'] = self.env['ir.sequence'].next_by_code('customer.id') or 'New'
        return super(Customer, self).create(vals)
    
    def action_send_birthday_email(self):
        """Gửi email chúc mừng sinh nhật cho khách hàng"""
        self.ensure_one()  # Đảm bảo chỉ xử lý một bản ghi
    
        if not self.email:
            raise ValidationError("Khách hàng này chưa có email!")
    
    # Tạo template email nếu chưa tồn tại
        template = self.env.ref('quan_ly_khach_hang.mail_template_customer_birthday', raise_if_not_found=False)
        if not template:
            template = self.env['mail.template'].create({
                'name': 'Chúc mừng sinh nhật khách hàng',
                'subject': 'Chúc mừng sinh nhật - {{ object.customer_name }}',
                'model_id': self.env['ir.model']._get('customer').id,
                'email_from': '${user.email_formatted | safe}',
                'email_to': '${object.email | safe}',
                'body_html': """
                    <div style="margin: 0px; padding: 0px;">
                        <p>Kính gửi <strong>${object.customer_name}</strong>,</p>
                        <p>Chúng tôi xin gửi lời chúc mừng sinh nhật tốt đẹp nhất đến bạn! 
                        Chúc bạn một ngày sinh nhật thật vui vẻ, hạnh phúc và thành công.</p>
                        <p>Cảm ơn bạn đã luôn đồng hành cùng chúng tôi.</p>
                        <p>Trân trọng,<br/>
                        Đội ngũ công ty chúng tôi</p>
                    </div>
                """,
            })
    
    # Gửi email
        template.send_mail(self.id, force_send=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Thành công',
                'message': f'Email chúc mừng sinh nhật đã được gửi tới {self.email}',
                'type': 'success',
                'sticky': False,
            }
        }

    # Thêm vào cuối class Customer trong customer.py
    def action_send_welcome_email(self):
        """Gửi email chào mừng cho khách hàng"""
        self.ensure_one()  # Đảm bảo chỉ xử lý một bản ghi
    
        if not self.email:
            raise ValidationError("Khách hàng này chưa có email!")
    
    # Tạo template email nếu chưa tồn tại
        template = self.env.ref('quan_ly_khach_hang.mail_template_customer_welcome', raise_if_not_found=False)
        if not template:
            template = self.env['mail.template'].create({
                'name': 'Chào mừng khách hàng mới',
                'subject': 'Chào mừng bạn đến với Công ty chúng tôi - {{ object.customer_name }}',
                'model_id': self.env['ir.model']._get('customer').id,
                'email_from': '${user.email_formatted | safe}',
                'email_to': '${object.email | safe}',
                'body_html': """
                    <div style="margin: 0px; padding: 0px;">
                        <p>Kính gửi <strong>${object.customer_name}</strong>,</p>
                        <p>Chào mừng bạn đến với Công ty chúng tôi! 
                        Chúng tôi rất vui được đồng hành cùng bạn trong hành trình sắp tới.</p>
                        <p>Nếu bạn có bất kỳ câu hỏi nào, đừng ngần ngại liên hệ với chúng tôi qua email này hoặc số điện thoại ${user.company_id.phone}.</p>
                        <p>Trân trọng,<br/>
                        Đội ngũ Công ty chúng tôi</p>
                    </div>
                """,
            })
    
    # Gửi email
        template.send_mail(self.id, force_send=True)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Thành công',
                'message': f'Email chào mừng đã được gửi tới {self.email}',
                'type': 'success',
                'sticky': False,
            }
    }

    #def action_send_welcome_email(self):
    #   """Gửi email chào mừng cho khách hàng"""
    #    self.ensure_one()   

    @api.depends('interact_ids')
    def _compute_recent_interactions(self):
        today = fields.Date.today()
        start_of_month = today.replace(day=1)
        for record in self:
            recent = record.interact_ids.filtered(
                lambda x: x.date and x.date.date() >= start_of_month
            )
            record.recent_interactions = len(recent)

    @api.model
    def recompute_customer_tiers(self):
        """Cron: force recompute tiers for all customers."""
        customers = self.search([])
        # Ensure aggregated fields are up to date
        customers._compute_total_sale_orders()
        customers._compute_total_amount()
        customers._compute_customer_tier()
        # Also recompute loyalty points to keep consistent with history
        try:
            customers.recompute_loyalty_points()
        except Exception:
            _logger.exception('Failed to recompute loyalty points during tier recompute')
        _logger.info('Recomputed customer tiers for %s customers', len(customers))

    @api.model
    def expire_loyalty_points(self, days=365):
        """Cron: expire loyalty points for customers with no orders in `days` days.

        Policy: if the customer's last order is older than `days`, set loyalty_points to 0.
        """
        today = fields.Datetime.context_timestamp(self, fields.Datetime.now()).date()
        cutoff = today - timedelta(days=days)
        customers = self.search([])
        expired = 0
        for c in customers:
            try:
                if not c.sale_order_ids:
                    # no orders -> expire
                    if c.loyalty_points:
                        c.write({'loyalty_points': 0})
                        expired += 1
                    continue
                # compute last order date (date portion)
                last_dates = [ (so.date_order.date() if isinstance(so.date_order, datetime) else fields.Datetime.to_datetime(so.date_order).date()) for so in c.sale_order_ids if so.date_order ]
                if not last_dates:
                    if c.loyalty_points:
                        c.write({'loyalty_points': 0})
                        expired += 1
                    continue
                last_order_date = max(last_dates)
                if last_order_date < cutoff and c.loyalty_points:
                    c.write({'loyalty_points': 0})
                    expired += 1
            except Exception:
                _logger.exception('Failed to evaluate/expire points for customer %s', c.id)
        _logger.info('Expired loyalty points for %s customers (cutoff=%s)', expired, cutoff)