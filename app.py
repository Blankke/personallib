from flask import Flask, request, jsonify, render_template, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
import json
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__)

# 配置数据库路径
project_dir = os.path.abspath(os.path.dirname(__file__))
database_path = os.path.join(project_dir, 'data', 'reviews.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# 确保data目录存在
os.makedirs(os.path.join(project_dir, 'data'), exist_ok=True)

# 定义数据库模型
class ColumnModel(db.Model):
    __tablename__ = 'columns'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    program_name = db.Column(db.String(100))
    editor = db.Column(db.String(50))
    responsible_editor = db.Column(db.String(50))
    broadcasters = db.Column(db.String(200))
    director = db.Column(db.String(50))

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    column_id = db.Column(db.Integer, db.ForeignKey('columns.id'))
    name = db.Column(db.String(100), nullable=False)       # 新增：姓名
    script = db.Column(db.String(200), nullable=False)     # 新增：稿件
    broadcast = db.Column(db.String(100), nullable=False)  # 新增：播音
    padding = db.Column(db.String(100), nullable=False)    # 新增：垫乐
    submit_time = db.Column(db.DateTime, default=db.func.current_timestamp())

# 初始化数据库
def init_db():
    with app.app_context():
        db.drop_all()  # 删除旧表（如果存在）
        db.create_all()

# 定时任务：更新栏目信息
def update_columns_from_log():
    log_path = os.path.join(project_dir, 'data', 'column_info.json')
    if os.path.exists(log_path):
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                log_data = json.load(f)
            if 'columns' not in log_data:
                raise KeyError("日志文件缺少 'columns' 键")
            
            with app.app_context():
                ColumnModel.query.delete()
                for column in log_data['columns']:
                    new_column = ColumnModel(
                        id=column['id'],
                        name=column['name'],
                        program_name=column['programName'],
                        editor=column['editor'],
                        responsible_editor=column['responsibleEditor'],
                        broadcasters=','.join(column['broadcasters']),
                        director=column['director']
                    )
                    db.session.add(new_column)
                db.session.commit()
            print(f"[{datetime.now()}] 栏目信息已更新！")
        except Exception as e:
            print(f"[{datetime.now()}] 更新失败：{str(e)}")
    else:
        print(f"[{datetime.now()}] 日志文件不存在！")

# 定时任务：每周日18点自动导出
def auto_export():
    try:
        with app.app_context():
            df = pd.read_sql_table('reviews', db.engine)
            df.rename(columns={
                'name': '姓名',
                'script': '稿件',
                'broadcast': '播音',
                'padding': '垫乐',
                'submit_time': '提交时间'
            }, inplace=True)
            export_path = os.path.join(project_dir, 'data', 'reviews_weekly.xlsx')
            df.to_excel(export_path, index=False)
        print(f"[{datetime.now()}] 数据已导出到 {export_path}")
    except Exception as e:
        print(f"[{datetime.now()}] 导出失败：{str(e)}")

# 启动定时任务
scheduler = BackgroundScheduler()
scheduler.add_job(update_columns_from_log, 'cron', day_of_week='sun', hour=0)
scheduler.add_job(auto_export, 'cron', day_of_week='sun', hour=18)
scheduler.start()

# 路由：主页
@app.route('/')
def index():
    return render_template('review_form.html')

# 路由：获取所有栏目
@app.route('/api/columns', methods=['GET'])
def get_columns():
    columns = ColumnModel.query.all()
    return jsonify([
        {'id': c.id, 'name': c.name} 
        for c in columns
    ])

# 路由：获取栏目详情
@app.route('/api/column/<int:column_id>', methods=['GET'])
def get_column_info(column_id):
    column = ColumnModel.query.get_or_404(column_id)
    return jsonify({
        'programName': column.program_name,
        'editor': column.editor,
        'responsibleEditor': column.responsible_editor,
        'broadcasters': column.broadcasters.split(','),
        'director': column.director
    })

# 路由：提交听评（新增四个字段）
@app.route('/api/submit', methods=['POST'])
def submit_review():
    try:
        data = request.json
        column_id = data.get('columnId')
        name = data.get('name')
        script = data.get('script')
        broadcast = data.get('broadcast')
        padding = data.get('padding')
        
        if not all([column_id, name, script, broadcast, padding]):
            return jsonify({'status': 'error', 'message': '缺少必要字段！'})
        
        # 检查栏目是否存在
        column = ColumnModel.query.get(column_id)
        if not column:
            return jsonify({'status': 'error', 'message': '无效的栏目ID！'})
        
        new_review = Review(
            column_id=column_id,
            name=name,
            script=script,
            broadcast=broadcast,
            padding=padding
        )
        with app.app_context():
            db.session.add(new_review)
            db.session.commit()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# 路由：导出数据
@app.route('/api/export', methods=['GET'])
def export_reviews():
    try:
        with app.app_context():
            df = pd.read_sql_table('reviews', db.engine)
            df.rename(columns={
                'name': '姓名',
                'script': '稿件',
                'broadcast': '播音',
                'padding': '垫乐',
                'submit_time': '提交时间'
            }, inplace=True)
            export_path = os.path.join(project_dir, 'data', 'reviews_export.xlsx')
            df.to_excel(export_path, index=False)
        return send_from_directory(
            directory=os.path.dirname(export_path),
            path=os.path.basename(export_path),
            as_attachment=True
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

# 路由：查询所有听评记录（显示栏目名称）
@app.route('/api/reviews', methods=['GET'])
def get_all_reviews():
    try:
        with app.app_context():
            # 使用JOIN查询获取栏目名称
            reviews = (
                db.session.query(
                    Review,
                    ColumnModel.name.label('column_name')
                )
                .join(ColumnModel, Review.column_id == ColumnModel.id)
                .all()
            )
            data = []
            for review, column_name in reviews:
                data.append({
                    '栏目名称': column_name,
                    '姓名': review.name,
                    '稿件': review.script,
                    '播音': review.broadcast,
                    '垫乐': review.padding,
                    '提交时间': review.submit_time.strftime('%Y-%m-%d %H:%M:%S')
                })
            response = make_response(json.dumps(data, ensure_ascii=False))
            response.headers['Content-Type'] = 'application/json; charset=utf-8'
            return response
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

if __name__ == '__main__':
    init_db()
    update_columns_from_log()
    app.run(debug=True)