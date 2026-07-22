"""Tests de la gestion des utilisateurs par l'administrateur."""

import os
import re
import tempfile
import unittest
from html import unescape

from app import create_app
from app.extensions import db
from app.models import Branch, User


class UserManagementTestCase(unittest.TestCase):
    """Vérifie la gestion sécurisée des utilisateurs common."""

    def setUp(self):
        """Prépare une application et une base SQLite temporaires."""
        # Crée un fichier SQLite temporaire.
        file_descriptor, self.database_path = tempfile.mkstemp(
            suffix=".db"
        )
        os.close(file_descriptor)

        # Crée une application réservée aux tests.
        self.app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": (
                    "cle-secrete-tests-gestion-utilisateurs-hbntory"
                ),
                "SQLALCHEMY_DATABASE_URI": (
                    f"sqlite:///{self.database_path}"
                ),
                "SESSION_COOKIE_SECURE": False,
                "WTF_CSRF_ENABLED": True,
            }
        )

        # Crée un client HTTP simulant un navigateur.
        self.client = self.app.test_client()

        # Crée les données nécessaires aux tests.
        with self.app.app_context():
            db.create_all()

            # Crée deux branches pour tester les changements
            # d'affectation des utilisateurs.
            toulouse = Branch(name="Toulouse")
            carcassonne = Branch(name="Carcassonne")

            db.session.add_all(
                [
                    toulouse,
                    carcassonne,
                ]
            )
            db.session.flush()

            # Crée l'unique compte administrateur.
            admin = User(
                username="superadmin",
                role="admin",
                is_active=True,
                branch_id=None,
            )
            admin.set_password("MotDePasseAdmin123!")

            # Crée un utilisateur common initial.
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

            # Conserve les identifiants nécessaires aux tests.
            self.admin_id = admin.id
            self.common_user_id = common_user.id
            self.toulouse_id = toulouse.id
            self.carcassonne_id = carcassonne.id

    def tearDown(self):
        """Supprime la base temporaire après chaque test."""
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

        # Supprime le fichier SQLite temporaire.
        if os.path.exists(self.database_path):
            os.remove(self.database_path)

    def get_csrf_token(self, response):
        """Extrait le jeton CSRF présent dans une page HTML."""
        html_content = response.get_data(as_text=True)

        # Recherche la valeur du champ CSRF dans le formulaire.
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
        # Charge d'abord la page pour obtenir un jeton CSRF.
        login_page = self.client.get("/auth/login")
        csrf_token = self.get_csrf_token(login_page)

        # Envoie les identifiants avec le jeton CSRF.
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
        # Charge la page contenant le formulaire.
        page = self.client.get(page_path)
        csrf_token = self.get_csrf_token(page)

        # Copie les données pour ne pas modifier
        # le dictionnaire original du test.
        form_data = dict(data)
        form_data["csrf_token"] = csrf_token

        # Envoie le formulaire vers sa route d'action.
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

        # Le compte common doit apparaître dans le tableau.
        self.assertIn(
            "<td>toulouse_user</td>",
            html_content,
        )

        # L'administrateur peut apparaître dans un message flash,
        # mais ne doit pas apparaître dans une cellule du tableau.
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

            # Vérifie les données du compte créé.
            self.assertIsNotNone(user)
            self.assertEqual(user.role, "common")
            self.assertTrue(user.is_active)
            self.assertEqual(
                user.branch_id,
                self.carcassonne_id,
            )

            # Le mot de passe en clair ne doit pas être enregistré.
            self.assertNotEqual(
                user.password_hash,
                "NouveauMotDePasse123!",
            )

            # Vérifie aussi que bcrypt accepte le mot de passe.
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

        # Le formulaire doit être réaffiché avec une erreur.
        self.assertEqual(response.status_code, 200)

        with self.app.app_context():
            common_users = db.session.scalars(
                db.select(User).where(
                    User.role == "common"
                )
            ).all()

            # Aucun doublon ne doit avoir été créé.
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

            # Le compte existe toujours, mais il est désactivé.
            self.assertIsNotNone(user)
            self.assertFalse(user.is_active)

    def test_admin_reactive_un_utilisateur(self):
        """Vérifie la réactivation d'un utilisateur."""
        # Désactive d'abord le compte directement en base.
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

        # Les routes de gestion ne recherchent que les common.
        self.assertEqual(response.status_code, 404)

    def test_common_ne_peut_pas_changer_un_statut(self):
        """Vérifie qu'un common ne peut pas désactiver un compte."""
        self.login(
            "toulouse_user",
            "MotDePasseToulouse123!",
        )

        # Le dashboard contient un jeton CSRF pour le logout.
        dashboard = self.client.get("/")
        csrf_token = self.get_csrf_token(dashboard)

        response = self.client.post(
            f"/admin/users/{self.common_user_id}/status",
            data={
                "csrf_token": csrf_token,
            },
        )

        # Le contrôle admin_required doit refuser l'accès.
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
