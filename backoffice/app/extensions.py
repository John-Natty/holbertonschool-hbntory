"""Extensions Flask partagées par le Backoffice."""

from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

# Instance SQLAlchemy utilisée pour communiquer avec PostgreSQL.
db = SQLAlchemy()

# Instance bcrypt utilisée pour hacher et vérifier les mots de passe.
bcrypt = Bcrypt()

# Instance utilisée pour gérer les migrations de la base de données.
migrate = Migrate()

# Instance utilisée pour gérer les sessions d'authentification.
login_manager = LoginManager()

# Instance utilisée pour protéger les formulaires contre les attaques CSRF.
csrf = CSRFProtect()
