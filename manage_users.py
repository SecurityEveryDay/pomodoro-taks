#!/usr/bin/env python3
"""
manage_users.py — CLI de administração de usuários do PomodoroFoco (SecDay)
===========================================================================
Permite ao administrador gerenciar usuários diretamente via linha de comando,
sem precisar acessar o painel web.

Uso:
    python manage_users.py list
    python manage_users.py reset-password <username_ou_email>
    python manage_users.py reset-password <username_ou_email> --senha <nova_senha>
    python manage_users.py set-admin <username_ou_email>
    python manage_users.py remove-admin <username_ou_email>
    python manage_users.py activate <username_ou_email>
    python manage_users.py deactivate <username_ou_email>
    python manage_users.py info <username_ou_email>
"""

import sys
import os
import sqlite3
import getpass
import argparse
from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

# ── Localizar o banco de dados ──────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(SCRIPT_DIR, 'pomodoro.db')


def get_db():
    if not os.path.exists(DATABASE):
        print(f"[ERRO] Banco de dados não encontrado em: {DATABASE}")
        print("  Execute a aplicação pelo menos uma vez para criar o banco.")
        sys.exit(1)
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def find_user(db, identifier):
    """Busca por username ou e-mail."""
    user = db.execute(
        "SELECT * FROM users WHERE username = ? OR email = ?",
        [identifier, identifier]
    ).fetchone()
    return user


def fmt_bool(val):
    return "✅ Sim" if val else "❌ Não"


# ── Comandos ────────────────────────────────────────────────────────────────

def cmd_list(args):
    """Lista todos os usuários cadastrados."""
    db = get_db()
    users = db.execute("""
        SELECT u.*,
               COUNT(DISTINCT t.id)  AS total_tasks,
               COUNT(DISTINCT ps.id) AS total_sessions
        FROM users u
        LEFT JOIN tasks t ON t.user_id = u.id
        LEFT JOIN pomodoro_sessions ps ON ps.user_id = u.id AND ps.is_completed = 1
        GROUP BY u.id
        ORDER BY u.id
    """).fetchall()

    if not users:
        print("Nenhum usuário cadastrado.")
        return

    col_w = [6, 20, 30, 7, 7, 6, 7]
    header = f"{'ID':<{col_w[0]}} {'Username':<{col_w[1]}} {'E-mail':<{col_w[2]}} {'Admin':<{col_w[3]}} {'Ativo':<{col_w[4]}} {'Tasks':<{col_w[5]}} {'Sessões':<{col_w[6]}}"
    print("\n" + "─" * len(header))
    print(header)
    print("─" * len(header))
    for u in users:
        admin_str = "SIM" if u['is_admin'] else "não"
        active_str = "SIM" if u['is_active'] else "não"
        print(
            f"{u['id']:<{col_w[0]}} {u['username']:<{col_w[1]}} "
            f"{u['email']:<{col_w[2]}} {admin_str:<{col_w[3]}} "
            f"{active_str:<{col_w[4]}} {u['total_tasks']:<{col_w[5]}} "
            f"{u['total_sessions']:<{col_w[6]}}"
        )
    print("─" * len(header))
    print(f"Total: {len(users)} usuário(s)\n")
    db.close()


def cmd_info(args):
    """Exibe detalhes de um usuário específico."""
    db = get_db()
    user = find_user(db, args.identificador)
    if not user:
        print(f"[ERRO] Usuário não encontrado: {args.identificador}")
        sys.exit(1)

    tasks = db.execute(
        "SELECT COUNT(*) as c, SUM(is_completed) as done FROM tasks WHERE user_id=?",
        [user['id']]
    ).fetchone()
    sessions = db.execute(
        "SELECT COUNT(*) as c, COALESCE(SUM(duration_minutes),0) as mins "
        "FROM pomodoro_sessions WHERE user_id=? AND is_completed=1 AND session_type='pomodoro'",
        [user['id']]
    ).fetchone()

    print(f"\n{'─'*40}")
    print(f"  Usuário   : {user['username']}  (ID: {user['id']})")
    print(f"  E-mail    : {user['email']}")
    print(f"  Admin     : {fmt_bool(user['is_admin'])}")
    print(f"  Ativo     : {fmt_bool(user['is_active'])}")
    print(f"  Cadastro  : {user['created_at'][:19] if user['created_at'] else '—'}")
    print(f"  Tarefas   : {tasks['c']} total, {tasks['done'] or 0} concluídas")
    print(f"  Sessões   : {sessions['c']} pomodoros ({sessions['mins']} min focados)")
    print(f"{'─'*40}\n")
    db.close()


def cmd_reset_password(args):
    """Redefine a senha de um usuário."""
    db = get_db()
    user = find_user(db, args.identificador)
    if not user:
        print(f"[ERRO] Usuário não encontrado: {args.identificador}")
        sys.exit(1)

    print(f"\nRedefinindo senha para: {user['username']} <{user['email']}>")

    if args.senha:
        new_pw = args.senha
        if len(new_pw) < 6:
            print("[ERRO] A senha deve ter pelo menos 6 caracteres.")
            sys.exit(1)
    else:
        # Interactive — prompt twice
        while True:
            new_pw = getpass.getpass("  Nova senha (mín. 6 caracteres): ")
            if len(new_pw) < 6:
                print("  ⚠  Senha muito curta. Tente novamente.")
                continue
            confirm = getpass.getpass("  Confirme a senha: ")
            if new_pw != confirm:
                print("  ⚠  As senhas não coincidem. Tente novamente.")
                continue
            break

    db.execute(
        "UPDATE users SET password_hash=? WHERE id=?",
        [generate_password_hash(new_pw), user['id']]
    )
    db.commit()
    print(f"  ✅ Senha atualizada com sucesso para o usuário '{user['username']}'.\n")
    db.close()


def cmd_set_admin(args):
    """Concede privilégios de administrador a um usuário."""
    db = get_db()
    user = find_user(db, args.identificador)
    if not user:
        print(f"[ERRO] Usuário não encontrado: {args.identificador}")
        sys.exit(1)
    if user['is_admin']:
        print(f"  ℹ  '{user['username']}' já é administrador.")
    else:
        db.execute("UPDATE users SET is_admin=1 WHERE id=?", [user['id']])
        db.commit()
        print(f"  ✅ '{user['username']}' agora é administrador.")
    db.close()


def cmd_remove_admin(args):
    """Remove privilégios de administrador de um usuário."""
    db = get_db()
    user = find_user(db, args.identificador)
    if not user:
        print(f"[ERRO] Usuário não encontrado: {args.identificador}")
        sys.exit(1)
    if not user['is_admin']:
        print(f"  ℹ  '{user['username']}' não é administrador.")
    else:
        db.execute("UPDATE users SET is_admin=0 WHERE id=?", [user['id']])
        db.commit()
        print(f"  ✅ Privilégios de admin removidos de '{user['username']}'.")
    db.close()


def cmd_activate(args):
    """Ativa a conta de um usuário."""
    db = get_db()
    user = find_user(db, args.identificador)
    if not user:
        print(f"[ERRO] Usuário não encontrado: {args.identificador}")
        sys.exit(1)
    if user['is_active']:
        print(f"  ℹ  '{user['username']}' já está ativo.")
    else:
        db.execute("UPDATE users SET is_active=1 WHERE id=?", [user['id']])
        db.commit()
        print(f"  ✅ Conta de '{user['username']}' reativada.")
    db.close()


def cmd_deactivate(args):
    """Desativa (bloqueia) a conta de um usuário."""
    db = get_db()
    user = find_user(db, args.identificador)
    if not user:
        print(f"[ERRO] Usuário não encontrado: {args.identificador}")
        sys.exit(1)
    if not user['is_active']:
        print(f"  ℹ  '{user['username']}' já está desativado.")
    else:
        confirm = input(f"  ⚠  Desativar '{user['username']}'? [s/N] ").strip().lower()
        if confirm not in ('s', 'sim', 'y', 'yes'):
            print("  Operação cancelada.")
        else:
            db.execute("UPDATE users SET is_active=0 WHERE id=?", [user['id']])
            db.commit()
            print(f"  ✅ Conta de '{user['username']}' desativada.")
    db.close()


# ── Parser ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="PomodoroFoco — CLI de Administração de Usuários (SecDay)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python manage_users.py list
  python manage_users.py info joao
  python manage_users.py reset-password joao@secday.com
  python manage_users.py reset-password joao --senha minhasenha123
  python manage_users.py set-admin maria
  python manage_users.py deactivate pedro
        """
    )
    sub = parser.add_subparsers(dest='command', metavar='COMANDO')
    sub.required = True

    # list
    p_list = sub.add_parser('list', help='Lista todos os usuários')
    p_list.set_defaults(func=cmd_list)

    # info
    p_info = sub.add_parser('info', help='Exibe detalhes de um usuário')
    p_info.add_argument('identificador', help='Username ou e-mail')
    p_info.set_defaults(func=cmd_info)

    # reset-password
    p_reset = sub.add_parser('reset-password', help='Redefine a senha de um usuário')
    p_reset.add_argument('identificador', help='Username ou e-mail')
    p_reset.add_argument('--senha', default=None,
                         help='Nova senha (se omitido, será solicitada interativamente)')
    p_reset.set_defaults(func=cmd_reset_password)

    # set-admin
    p_sa = sub.add_parser('set-admin', help='Concede privilégios de admin')
    p_sa.add_argument('identificador', help='Username ou e-mail')
    p_sa.set_defaults(func=cmd_set_admin)

    # remove-admin
    p_ra = sub.add_parser('remove-admin', help='Remove privilégios de admin')
    p_ra.add_argument('identificador', help='Username ou e-mail')
    p_ra.set_defaults(func=cmd_remove_admin)

    # activate
    p_ac = sub.add_parser('activate', help='Reativa a conta de um usuário')
    p_ac.add_argument('identificador', help='Username ou e-mail')
    p_ac.set_defaults(func=cmd_activate)

    # deactivate
    p_de = sub.add_parser('deactivate', help='Desativa a conta de um usuário')
    p_de.add_argument('identificador', help='Username ou e-mail')
    p_de.set_defaults(func=cmd_deactivate)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
