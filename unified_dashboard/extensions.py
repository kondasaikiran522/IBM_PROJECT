from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

socketio = SocketIO(cors_allowed_origins="*")
db = SQLAlchemy()
