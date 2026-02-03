from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from sqlalchemy import extract, func
from calendar import month_name
import os

# Inicializar Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
# Usar PostgreSQL em produção, SQLite em desenvolvimento
database_url = os.getenv('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Inicializar banco de dados
db = SQLAlchemy(app)

# Inicializar gerenciador de login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'

# Modelo de Usuário
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Carregar usuário
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Criar banco de dados
with app.app_context():
    db.create_all()

# Rota: Página inicial
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

# Rota: Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash('Login realizado com sucesso!', 'success')
            
            # Redirecionar para página solicitada ou dashboard
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Email ou senha incorretos.', 'danger')
    
    return render_template('login.html')

# Rota: Registro
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validações
        if password != confirm_password:
            flash('As senhas não coincidem.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(email=email).first():
            flash('Este email já está cadastrado.', 'danger')
            return render_template('register.html')
        
        if User.query.filter_by(username=username).first():
            flash('Este nome de usuário já existe.', 'danger')
            return render_template('register.html')
        
        # Criar novo usuário
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Conta criada com sucesso! Faça login.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Rota: Dashboard (protegida)
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', username=current_user.username)

# Rota: Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('login'))


# Adicione após a classe User
class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamento com usuário
    user = db.relationship('User', backref=db.backref('expenses', lazy=True))
    
# Rota: Página de Gastos
@app.route('/expenses')
@login_required
def expenses():
    # Buscar todas as despesas do usuário
    user_expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).all()
    
    # Calcular total de gastos
    total = sum(expense.amount for expense in user_expenses)
    
    # Calcular total por categoria
    categories = {}
    for expense in user_expenses:
        if expense.category in categories:
            categories[expense.category] += expense.amount
        else:
            categories[expense.category] = expense.amount
    
    return render_template('expenses.html', 
                         expenses=user_expenses, 
                         total=total,
                         categories=categories)

# Rota: Adicionar Gasto
@app.route('/expenses/add', methods=['POST'])
@login_required
def add_expense():
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    date_str = request.form.get('date')
    
    # Validações
    if not description or not amount or not category or not date_str:
        flash('Todos os campos são obrigatórios.', 'danger')
        return redirect(url_for('expenses'))
    
    try:
        amount = float(amount)
        if amount <= 0:
            flash('O valor deve ser maior que zero.', 'danger')
            return redirect(url_for('expenses'))
        
        # Converter string de data para objeto date
        expense_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Criar nova despesa
        new_expense = Expense(
            user_id=current_user.id,
            description=description,
            amount=amount,
            category=category,
            date=expense_date
        )
        
        db.session.add(new_expense)
        db.session.commit()
        
        flash('Gasto adicionado com sucesso!', 'success')
    except ValueError:
        flash('Valor ou data inválidos.', 'danger')
    
    return redirect(url_for('expenses'))

# Rota: Deletar Gasto
@app.route('/expenses/delete/<int:id>')
@login_required
def delete_expense(id):
    expense = Expense.query.get_or_404(id)
    
    # Verificar se o gasto pertence ao usuário
    if expense.user_id != current_user.id:
        flash('Você não tem permissão para deletar este gasto.', 'danger')
        return redirect(url_for('expenses'))
    
    db.session.delete(expense)
    db.session.commit()
    
    flash('Gasto deletado com sucesso!', 'success')
    return redirect(url_for('expenses'))

# Rota: Editar Gasto
@app.route('/expenses/edit/<int:id>', methods=['POST'])
@login_required
def edit_expense(id):
    expense = Expense.query.get_or_404(id)
    
    # Verificar se o gasto pertence ao usuário
    if expense.user_id != current_user.id:
        flash('Você não tem permissão para editar este gasto.', 'danger')
        return redirect(url_for('expenses'))
    
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    date_str = request.form.get('date')
    
    try:
        expense.description = description
        expense.amount = float(amount)
        expense.category = category
        expense.date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        db.session.commit()
        flash('Gasto atualizado com sucesso!', 'success')
    except ValueError:
        flash('Valor ou data inválidos.', 'danger')
    
    return redirect(url_for('expenses'))

# Adicione após a classe Expense
class Income(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamento com usuário
    user = db.relationship('User', backref=db.backref('incomes', lazy=True))


# Rota: Página de Receitas
@app.route('/incomes')
@login_required
def incomes():
    # Buscar todas as receitas do usuário
    user_incomes = Income.query.filter_by(user_id=current_user.id).order_by(Income.date.desc()).all()
    
    # Calcular total de receitas
    total = sum(income.amount for income in user_incomes)
    
    # Calcular total por categoria
    categories = {}
    for income in user_incomes:
        if income.category in categories:
            categories[income.category] += income.amount
        else:
            categories[income.category] = income.amount
    
    return render_template('incomes.html', 
                         incomes=user_incomes, 
                         total=total,
                         categories=categories)

# Rota: Adicionar Receita
@app.route('/incomes/add', methods=['POST'])
@login_required
def add_income():
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    date_str = request.form.get('date')
    
    # Validações
    if not description or not amount or not category or not date_str:
        flash('Todos os campos são obrigatórios.', 'danger')
        return redirect(url_for('incomes'))
    
    try:
        amount = float(amount)
        if amount <= 0:
            flash('O valor deve ser maior que zero.', 'danger')
            return redirect(url_for('incomes'))
        
        # Converter string de data para objeto date
        income_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Criar nova receita
        new_income = Income(
            user_id=current_user.id,
            description=description,
            amount=amount,
            category=category,
            date=income_date
        )
        
        db.session.add(new_income)
        db.session.commit()
        
        flash('Receita adicionada com sucesso!', 'success')
    except ValueError:
        flash('Valor ou data inválidos.', 'danger')
    
    return redirect(url_for('incomes'))

# Rota: Deletar Receita
@app.route('/incomes/delete/<int:id>')
@login_required
def delete_income(id):
    income = Income.query.get_or_404(id)
    
    # Verificar se a receita pertence ao usuário
    if income.user_id != current_user.id:
        flash('Você não tem permissão para deletar esta receita.', 'danger')
        return redirect(url_for('incomes'))
    
    db.session.delete(income)
    db.session.commit()
    
    flash('Receita deletada com sucesso!', 'success')
    return redirect(url_for('incomes'))

# Rota: Editar Receita
@app.route('/incomes/edit/<int:id>', methods=['POST'])
@login_required
def edit_income(id):
    income = Income.query.get_or_404(id)
    
    # Verificar se a receita pertence ao usuário
    if income.user_id != current_user.id:
        flash('Você não tem permissão para editar esta receita.', 'danger')
        return redirect(url_for('incomes'))
    
    description = request.form.get('description')
    amount = request.form.get('amount')
    category = request.form.get('category')
    date_str = request.form.get('date')
    
    try:
        income.description = description
        income.amount = float(amount)
        income.category = category
        income.date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        db.session.commit()
        flash('Receita atualizada com sucesso!', 'success')
    except ValueError:
        flash('Valor ou data inválidos.', 'danger')
    
    return redirect(url_for('incomes'))

# Rota: Dashboard Financeiro
@app.route('/financial-dashboard')
@login_required
def financial_dashboard():
    current_year = datetime.now().year
    current_month = datetime.now().month
    
    # Obter ano selecionado (se fornecido)
    selected_year = request.args.get('year', current_year, type=int)
    
    # Dados mensais do ano selecionado
    monthly_data = []
    for month in range(1, 13):
        # Gastos do mês
        expenses_sum = db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            extract('year', Expense.date) == selected_year,
            extract('month', Expense.date) == month
        ).scalar() or 0
        
        # Receitas do mês
        incomes_sum = db.session.query(func.sum(Income.amount)).filter(
            Income.user_id == current_user.id,
            extract('year', Income.date) == selected_year,
            extract('month', Income.date) == month
        ).scalar() or 0
        
        balance = incomes_sum - expenses_sum
        
        monthly_data.append({
            'month': month,
            'month_name': ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 
                          'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'][month-1],
            'expenses': float(expenses_sum),
            'incomes': float(incomes_sum),
            'balance': float(balance)
        })
    
    # Dados anuais (últimos 5 anos)
    yearly_data = []
    for year in range(selected_year - 4, selected_year + 1):
        # Gastos do ano
        expenses_sum = db.session.query(func.sum(Expense.amount)).filter(
            Expense.user_id == current_user.id,
            extract('year', Expense.date) == year
        ).scalar() or 0
        
        # Receitas do ano
        incomes_sum = db.session.query(func.sum(Income.amount)).filter(
            Income.user_id == current_user.id,
            extract('year', Income.date) == year
        ).scalar() or 0
        
        balance = incomes_sum - expenses_sum
        
        yearly_data.append({
            'year': year,
            'expenses': float(expenses_sum),
            'incomes': float(incomes_sum),
            'balance': float(balance)
        })
    
    # Gastos por categoria (ano selecionado)
    expenses_by_category = db.session.query(
        Expense.category, 
        func.sum(Expense.amount)
    ).filter(
        Expense.user_id == current_user.id,
        extract('year', Expense.date) == selected_year
    ).group_by(Expense.category).all()
    
    expense_categories = {cat: float(amount) for cat, amount in expenses_by_category}
    
    # Receitas por categoria (ano selecionado)
    incomes_by_category = db.session.query(
        Income.category, 
        func.sum(Income.amount)
    ).filter(
        Income.user_id == current_user.id,
        extract('year', Income.date) == selected_year
    ).group_by(Income.category).all()
    
    income_categories = {cat: float(amount) for cat, amount in incomes_by_category}
    
    # Totais gerais
    total_expenses = sum(month['expenses'] for month in monthly_data)
    total_incomes = sum(month['incomes'] for month in monthly_data)
    total_balance = total_incomes - total_expenses
    
    return render_template('financial_dashboard.html',
                         monthly_data=monthly_data,
                         yearly_data=yearly_data,
                         expense_categories=expense_categories,
                         income_categories=income_categories,
                         total_expenses=total_expenses,
                         total_incomes=total_incomes,
                         total_balance=total_balance,
                         selected_year=selected_year,
                         current_year=current_year)


with app.app_context():
    db.create_all()
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)