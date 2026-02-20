#!/usr/bin/env python3
"""
PomodoroFoco - Sistema de Gerenciamento de Produtividade
Execute: python run.py
Acesse: http://localhost:5000

"""

from app import app, init_db

if __name__ == '__main__':
    print("=" * 50)
    print("🍅  PomodoroFoco — Iniciando...")
    print("=" * 50)
    init_db()
    print("✅  Banco de dados inicializado")
    print("🌐  Acesse: http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host='0.0.0.0', port=5000)
