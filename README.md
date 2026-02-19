# 🍅 PomodoroFoco

Sistema de Gerenciamento de Produtividade baseado na técnica Pomodoro.

## 🚀 Como Executar

```bash
# Instalar dependências
pip install flask werkzeug

# Iniciar o servidor
python run.py

# Acesse no navegador
http://localhost:5000
```

## 👤 Conta de Demonstração
- **E-mail:** demo@teste.com  
- **Senha:** demo123

## 📁 Estrutura do Projeto

```
pomodoro/
├── app.py              # Aplicação Flask principal (rotas, models, lógica)
├── run.py              # Script de inicialização
├── requirements.txt    # Dependências Python
├── pomodoro.db         # Banco SQLite (criado automaticamente)
└── templates/
    ├── base.html       # Layout base (sidebar, navegação, estilos)
    ├── login.html      # Página de login
    ├── register.html   # Página de cadastro
    ├── dashboard.html  # Dashboard principal
    ├── timer.html      # Timer Pomodoro interativo
    ├── tasks.html      # Gestão de tarefas
    ├── projects.html   # Gestão de projetos
    ├── reports.html    # Relatórios e análises
    └── settings.html   # Configurações do usuário
```

## ✨ Funcionalidades

### 🔐 Autenticação
- Cadastro com username, e-mail e senha (hash bcrypt via Werkzeug)
- Login/logout com sessão Flask
- Dados isolados por usuário

### ⏱️ Timer Pomodoro
- Modos: Pomodoro (foco), Pausa Curta, Pausa Longa
- Controles: Iniciar, Pausar, Resetar, Pular
- Anel visual de progresso SVG animado
- Contador de pomodoros no ciclo (bolinhas)
- Som ao finalizar sessão (Web Audio API)
- Associar sessão a uma tarefa
- Registro automático no banco de dados
- Transição automática entre modos

### 📋 Gestão de Tarefas
- Criar, editar, excluir tarefas
- Campos: título, notas, tags, projeto, prioridade, estimativa de pomodoros
- Marcar como concluída / reabrir
- Visualizar progresso (X/Y pomodoros)
- Filtros por status, projeto, prioridade e tag

### 📁 Projetos
- Criar e gerenciar projetos com cores personalizadas
- Métricas por projeto: tarefas, concluídas, pomodoros
- Barra de progresso de conclusão

### 📊 Relatórios
- Períodos: Hoje, Semana, Mês, Ano, Personalizado
- Estatísticas: pomodoros, horas focadas, tarefas, projetos
- Gráfico de barras por dia
- Distribuição por projeto (barra horizontal)
- Distribuição por tag
- Tabela detalhada de tarefas trabalhadas
- Filtros por projeto, tag e prioridade

### ⚙️ Configurações
- Duração do Pomodoro, Pausa Curta e Longa (personalizável)
- Número de pausas antes da pausa longa
- Metas diária e semanal de pomodoros
- Modo escuro / claro
- Som on/off
- Alteração de senha

## 🗄️ Banco de Dados (SQLite)

Tabelas:
- **users** — usuários com configurações embutidas
- **projects** — projetos com cor
- **tasks** — tarefas com todos os campos
- **pomodoro_sessions** — histórico de sessões

## 🛠️ Tecnologias
- **Backend:** Python 3 + Flask
- **Banco:** SQLite (nativo Python)
- **Autenticação:** Sessões Flask + Werkzeug password hashing
- **Frontend:** HTML5 + CSS3 + JavaScript vanilla
- **Fontes:** Space Mono + DM Sans (Google Fonts)
- **Timer:** SVG circular animado + Web Audio API
