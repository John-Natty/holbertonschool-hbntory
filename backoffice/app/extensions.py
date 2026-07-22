"""Extensions Flask partagées."""

from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# Instance SQLAlchemy partagée.
db = SQLAlchemy()

# Instance bcrypt partagée.
bcrypt = Bcrypt()

# Instance utilisée pour gérer les migrations.
migrate = Migrate()
