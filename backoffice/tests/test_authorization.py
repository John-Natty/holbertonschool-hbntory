"""Tests automatisés des autorisations du Backoffice."""

import unittest

from app import create_app
from app.auth.decorators import (
    admin_required,
    common_required,
    own_branch_required,
)
from app.extensions import db
from app.models import Branch, User
from tests.test_helpers import (
    clean_test_database,
    get_test_database_url,
)


class AuthorizationTestCase(unittest.TestCase):
    """Vérifie les autorisations selon le rôle et la branche."""

    def setUp(self):
        """Prépare les données dans PostgreSQL avant chaque test."""
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": (
                    "cle-secrete-reservee-aux-tests-autorisation"
                ),
                "SQLALCHEMY_DATABASE_URI": (
                    get_test_database_url()
                ),
                "SESSION_COOKIE_SECURE": False,
                "WTF_CSRF_ENABLED": False,
            }
        )

        # Ajoute des routes utilisées uniquement par les tests.
        self.register_test_routes()

        # Crée un client simulant un navigateur.
        self.client = self.app.test_client()

        with self.app.app_context():
            # Garde le schéma PostgreSQL et nettoie uniquement
            # les données laissées par un précédent test.
            clean_test_database()

            branch_one = Branch(name="Toulouse")
            branch_two = Branch(name="Carcassonne")

            db.session.add_all(
                [
                    branch_one,
                    branch_two,
                ]
            )
            db.session.flush()

            admin = User(
                username="admin",
                role="admin",
                is_active=True,
                branch_id=None,
            )
            admin.set_password("MotDePasseAdmin123!")

            toulouse_user = User(
                username="toulouse_user",
                role="common",
                is_active=True,
                branch_id=branch_one.id,
            )
            toulouse_user.set_password(
                "MotDePasseToulouse123!"
            )

            carcassonne_user = User(
                username="carcassonne_user",
                role="common",
                is_active=True,
                branch_id=branch_two.id,
            )
            carcassonne_user.set_password(
                "MotDePasseCarcassonne123!"
            )

            db.session.add_all(
                [
                    admin,
                    toulouse_user,
                    carcassonne_user,
                ]
            )
            db.session.commit()

            # Conserve les identifiants nécessaires aux tests.
            self.toulouse_branch_id = branch_one.id
            self.carcassonne_branch_id = branch_two.id

    def tearDown(self):
        """Nettoie les données sans supprimer les tables."""
        with self.app.app_context():
            # Annule une éventuelle transaction incomplète.
            db.session.rollback()

            # Supprime uniquement les données de hbntory_test.
            clean_test_database()
            db.session.remove()

    def register_test_routes(self):
        """Ajoute des routes protégées uniquement pour les tests."""

        @self.app.route("/test/admin")
        @admin_required
        def admin_page():
            """Simule une page réservée à l'administrateur."""
            return "Page administrateur"

        @self.app.route("/test/common")
        @common_required
        def common_page():
            """Simule une page réservée aux utilisateurs communs."""
            return "Page utilisateur commun"

        @self.app.route(
            "/test/branches/<int:branch_id>/stock"
        )
        @own_branch_required
        def branch_stock_page(branch_id):
            """Simule une page stock limitée à une branche."""
            return f"Stock de la branche {branch_id}"

    def login(self, username, password):
        """Connecte un utilisateur pour les tests."""
        return self.client.post(
            "/auth/login",
            data={
                "username": username,
                "password": password,
            },
            follow_redirects=False,
        )

    def test_visiteur_anonyme_redirige_vers_connexion(self):
        """Vérifie la protection des routes pour les anonymes."""
        response = self.client.get(
            "/test/admin",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)

    def test_admin_autorise_sur_page_admin(self):
        """Vérifie qu'un administrateur accède à l'administration."""
        self.login(
            "admin",
            "MotDePasseAdmin123!",
        )

        response = self.client.get("/test/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Page administrateur",
            response.get_data(as_text=True),
        )

    def test_common_refuse_sur_page_admin(self):
        """Vérifie qu'un utilisateur commun ne devient pas admin."""
        self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        response = self.client.get("/test/admin")

        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "Accès interdit",
            response.get_data(as_text=True),
        )

    def test_common_autorise_sur_page_stock(self):
        """Vérifie qu'un utilisateur common accède au stock."""
        self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        response = self.client.get("/test/common")

        self.assertEqual(response.status_code, 200)

    def test_admin_refuse_sur_page_stock(self):
        """Vérifie qu'un administrateur ne gère pas le stock."""
        self.login(
            "admin",
            "MotDePasseAdmin123!",
        )

        response = self.client.get("/test/common")

        self.assertEqual(response.status_code, 403)

    def test_common_accede_a_sa_propre_branche(self):
        """Vérifie l'accès à la branche de l'utilisateur."""
        self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        response = self.client.get(
            (
                "/test/branches/"
                f"{self.toulouse_branch_id}/stock"
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            str(self.toulouse_branch_id),
            response.get_data(as_text=True),
        )

    def test_common_refuse_sur_une_autre_branche(self):
        """Vérifie le blocage des accès inter-branches."""
        self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        response = self.client.get(
            (
                "/test/branches/"
                f"{self.carcassonne_branch_id}/stock"
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_admin_refuse_sur_stock_de_branche(self):
        """Vérifie que l'administrateur ne gère aucune branche."""
        self.login(
            "admin",
            "MotDePasseAdmin123!",
        )

        response = self.client.get(
            (
                "/test/branches/"
                f"{self.toulouse_branch_id}/stock"
            )
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
