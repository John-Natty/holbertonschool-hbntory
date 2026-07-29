"""Tests de la gestion des utilisateurs par l'administrateur."""

import re
import unittest
from html import unescape

from app import create_app
from app.extensions import db
from app.models import Branch, User
from tests.test_helpers import (
    clean_test_database,
    get_test_database_url,
)


class UserManagementTestCase(unittest.TestCase):
    """Vérifie la gestion sécurisée des utilisateurs common."""

    def setUp(self):
        """Prépare les données dans PostgreSQL avant chaque test."""
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": (
                    "cle-secrete-tests-gestion-utilisateurs-hbntory"
                ),
                "SQLALCHEMY_DATABASE_URI": (
                    get_test_database_url()
                ),
                "SESSION_COOKIE_SECURE": False,
                "WTF_CSRF_ENABLED": True,
            }
        )

        self.client = self.app.test_client()

        with self.app.app_context():
            # Conserve le schéma et nettoie uniquement les données.
            clean_test_database()

            toulouse = Branch(name="Toulouse")
            carcassonne = Branch(name="Carcassonne")

            db.session.add_all(
                [
                    toulouse,
                    carcassonne,
                ]
            )
            db.session.flush()

            admin = User(
                username="superadmin",
                role="admin",
                is_active=True,
                branch_id=None,
            )
            admin.set_password("MotDePasseAdmin123!")

            common_user = User(
                username="toulouse_user",
                role="common",
                is_active=True,
                branch_id=toulouse.id,
            )
            common_user.set_password(
                "MotDePasseToulouse123!"
            )

            db.session.add_all(
                [
                    admin,
                    common_user,
                ]
            )
            db.session.commit()

            self.admin_id = admin.id
            self.common_user_id = common_user.id
            self.toulouse_id = toulouse.id
            self.carcassonne_id = carcassonne.id

    def tearDown(self):
        """Nettoie les données sans supprimer les tables."""
        with self.app.app_context():
            db.session.rollback()
            clean_test_database()
            db.session.remove()

    def get_csrf_token(self, response):
        """Extrait le jeton CSRF présent dans une page HTML."""
        html_content = response.get_data(as_text=True)

        match = re.search(
            r'name="csrf_token"[^>]*value="([^"]+)"',
            html_content,
        )

        self.assertIsNotNone(
            match,
            "Aucun jeton CSRF n'a été trouvé.",
        )

        return unescape(match.group(1))

    def login(self, username, password):
        """Connecte un utilisateur avec un jeton CSRF valide."""
        login_page = self.client.get("/auth/login")
        csrf_token = self.get_csrf_token(login_page)

        return self.client.post(
            "/auth/login",
            data={
                "username": username,
                "password": password,
                "csrf_token": csrf_token,
            },
            follow_redirects=False,
        )

    def post_form(self, page_path, action_path, data):
        """Envoie un formulaire avec un jeton CSRF valide."""
        page = self.client.get(page_path)
        csrf_token = self.get_csrf_token(page)

        form_data = dict(data)
        form_data["csrf_token"] = csrf_token

        return self.client.post(
            action_path,
            data=form_data,
            follow_redirects=False,
        )

    def test_anonyme_redirige_vers_connexion(self):
        """Vérifie que l'administration nécessite une connexion."""
        response = self.client.get(
            "/admin/users",
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/auth/login", response.location)

    def test_common_refuse_sur_administration(self):
        """Vérifie qu'un common ne peut pas gérer les utilisateurs."""
        self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        response = self.client.get("/admin/users")

        self.assertEqual(response.status_code, 403)

    def test_admin_liste_uniquement_les_common(self):
        """Vérifie que l'admin ne se gère pas lui-même."""
        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        response = self.client.get("/admin/users")
        html_content = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "<td>toulouse_user</td>",
            html_content,
        )
        self.assertNotIn(
            "<td>superadmin</td>",
            html_content,
        )

    def test_admin_cree_un_utilisateur_common(self):
        """Vérifie la création d'un utilisateur common."""
        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        response = self.post_form(
            "/admin/users/create",
            "/admin/users/create",
            {
                "username": "nouvel_utilisateur",
                "password": "NouveauMotDePasse123!",
                "confirm_password": "NouveauMotDePasse123!",
                "branch_id": str(self.carcassonne_id),
            },
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            user = db.session.scalar(
                db.select(User).where(
                    User.username == "nouvel_utilisateur"
                )
            )

            self.assertIsNotNone(user)
            self.assertEqual(user.role, "common")
            self.assertTrue(user.is_active)
            self.assertEqual(
                user.branch_id,
                self.carcassonne_id,
            )
            self.assertNotEqual(
                user.password_hash,
                "NouveauMotDePasse123!",
            )
            self.assertTrue(
                user.check_password(
                    "NouveauMotDePasse123!"
                )
            )

    def test_username_duplicate_refuse(self):
        """Vérifie l'unicité du username sans tenir compte de la casse."""
        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        response = self.post_form(
            "/admin/users/create",
            "/admin/users/create",
            {
                "username": "TOULOUSE_USER",
                "password": "AutreMotDePasse123!",
                "confirm_password": "AutreMotDePasse123!",
                "branch_id": str(self.toulouse_id),
            },
        )

        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            common_users = db.session.scalars(
                db.select(User).where(
                    User.role == "common"
                )
            ).all()

            self.assertEqual(len(common_users), 1)

    def test_creation_sans_csrf_refusee(self):
        """Vérifie que la création nécessite un jeton CSRF."""
        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        response = self.client.post(
            "/admin/users/create",
            data={
                "username": "nouvel_utilisateur",
                "password": "NouveauMotDePasse123!",
                "confirm_password": "NouveauMotDePasse123!",
                "branch_id": str(self.toulouse_id),
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_admin_modifie_un_utilisateur(self):
        """Vérifie la modification du username et de la branche."""
        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        edit_path = (
            f"/admin/users/{self.common_user_id}/edit"
        )

        response = self.post_form(
            edit_path,
            edit_path,
            {
                "username": "utilisateur_modifie",
                "password": "",
                "confirm_password": "",
                "branch_id": str(self.carcassonne_id),
            },
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            user = db.session.get(
                User,
                self.common_user_id,
            )

            self.assertEqual(
                user.username,
                "utilisateur_modifie",
            )
            self.assertEqual(
                user.branch_id,
                self.carcassonne_id,
            )

    def test_mot_de_passe_vide_conserve_le_hash(self):
        """Vérifie qu'un champ vide conserve le mot de passe."""
        with self.app.app_context():
            user = db.session.get(
                User,
                self.common_user_id,
            )
            previous_hash = user.password_hash

        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        edit_path = (
            f"/admin/users/{self.common_user_id}/edit"
        )

        response = self.post_form(
            edit_path,
            edit_path,
            {
                "username": "toulouse_user",
                "password": "",
                "confirm_password": "",
                "branch_id": str(self.toulouse_id),
            },
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            user = db.session.get(
                User,
                self.common_user_id,
            )

            self.assertEqual(
                user.password_hash,
                previous_hash,
            )

    def test_admin_desactive_sans_supprimer(self):
        """Vérifie la désactivation sans suppression physique."""
        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        action_path = (
            f"/admin/users/{self.common_user_id}/status"
        )

        response = self.post_form(
            "/admin/users",
            action_path,
            {},
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            user = db.session.get(
                User,
                self.common_user_id,
            )

            self.assertIsNotNone(user)
            self.assertFalse(user.is_active)

    def test_utilisateur_desactive_par_admin_ne_se_connecte_plus(self):
        """Refuse la connexion après une désactivation administrative."""

        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        action_path = (
            f"/admin/users/{self.common_user_id}/status"
        )
        response = self.post_form(
            "/admin/users",
            action_path,
            {},
        )

        self.assertEqual(response.status_code, 302)

        with self.client.session_transaction() as session:
            session.clear()

        response = self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "Nom d&#39;utilisateur ou mot de passe incorrect.",
            response.get_data(as_text=True),
        )

        with self.client.session_transaction() as session:
            self.assertNotIn("_user_id", session)

    def test_admin_reactive_un_utilisateur(self):
        """Vérifie la réactivation d'un utilisateur."""
        with self.app.app_context():
            user = db.session.get(
                User,
                self.common_user_id,
            )
            user.is_active = False
            db.session.commit()

        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        action_path = (
            f"/admin/users/{self.common_user_id}/status"
        )

        response = self.post_form(
            "/admin/users",
            action_path,
            {},
        )

        self.assertEqual(response.status_code, 302)

        with self.app.app_context():
            user = db.session.get(
                User,
                self.common_user_id,
            )

            self.assertTrue(user.is_active)

    def test_admin_ne_peut_pas_modifier_un_admin(self):
        """Vérifie que les routes refusent un compte admin."""
        self.login(
            "superadmin",
            "MotDePasseAdmin123!",
        )

        response = self.client.get(
            f"/admin/users/{self.admin_id}/edit"
        )

        self.assertEqual(response.status_code, 404)

    def test_common_ne_peut_pas_changer_un_statut(self):
        """Vérifie qu'un common ne peut pas désactiver un compte."""
        self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        dashboard = self.client.get("/")
        csrf_token = self.get_csrf_token(dashboard)

        response = self.client.post(
            f"/admin/users/{self.common_user_id}/status",
            data={
                "csrf_token": csrf_token,
            },
        )

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
