#!/bin/bash
# ============================================================
#  AGENT ARMY — drop in any project, run ./army.sh
#  Bouwt een zelfverbeterend team van Claude agents dat 24/7
#  je project analyseert, bouwt, test en deployed.
# ============================================================
set -euo pipefail

# ── Kleuren voor output ──────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${CYAN}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
err()  { echo -e "${RED}✗${NC} $1"; exit 1; }
head() { echo -e "\n${BOLD}${BLUE}══ $1 ══${NC}"; }

# ── Config ───────────────────────────────────────────────────
ARMY_DIR=".army"
ENV_FILE="$ARMY_DIR/.env"
LOG_DIR="$ARMY_DIR/logs"
TASK_DIR="$ARMY_DIR/tasks"
REPORT_DIR="$ARMY_DIR/reports"
API="https://api.anthropic.com/v1"
BETA="managed-agents-2026-04-01"
MODEL="claude-sonnet-4-6"
LOOP_INTERVAL=60  # seconden tussen orchestratie cycli

# ── Vereisten checken ────────────────────────────────────────
check_deps() {
  head "Vereisten checken"
  command -v curl >/dev/null || err "curl niet gevonden"
  command -v jq   >/dev/null || err "jq niet gevonden — installeer: brew install jq"
  [[ -z "${ANTHROPIC_API_KEY:-}" ]] && err "ANTHROPIC_API_KEY niet gezet. Doe: export ANTHROPIC_API_KEY=sk-ant-..."
  ok "Alle vereisten aanwezig"
}

# ── Project context detecteren ───────────────────────────────
detect_project() {
  head "Project detecteren"
  PROJECT_DIR=$(pwd)
  PROJECT_NAME=$(basename "$PROJECT_DIR")

  TECH_STACK=""
  [[ -f "package.json" ]]      && TECH_STACK="$TECH_STACK Node.js/JavaScript"
  [[ -f "requirements.txt" ]]  && TECH_STACK="$TECH_STACK Python"
  [[ -f "Cargo.toml" ]]        && TECH_STACK="$TECH_STACK Rust"
  [[ -f "go.mod" ]]            && TECH_STACK="$TECH_STACK Go"
  [[ -f "composer.json" ]]     && TECH_STACK="$TECH_STACK PHP"
  [[ -d ".claude" ]]           && TECH_STACK="$TECH_STACK Claude-Code-project"
  [[ -f "CLAUDE.md" ]]         && HAS_CLAUDE_MD=true || HAS_CLAUDE_MD=false

  GITHUB_REMOTE=""
  if git remote get-url origin &>/dev/null 2>&1; then
    GITHUB_REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
    # Converteer SSH naar HTTPS als nodig
    GITHUB_REMOTE=$(echo "$GITHUB_REMOTE" | sed 's|git@github.com:|https://github.com/|' | sed 's|\.git$||')
  fi

  log "Project: ${BOLD}$PROJECT_NAME${NC}"
  log "Stack:   ${BOLD}$TECH_STACK${NC}"
  log "GitHub:  ${BOLD}${GITHUB_REMOTE:-niet gevonden}${NC}"
  log "CLAUDE.md: ${BOLD}$HAS_CLAUDE_MD${NC}"
}

# ── API helper ───────────────────────────────────────────────
api_call() {
  local method=$1 endpoint=$2 data=${3:-"{}"}
  curl -sS -X "$method" "$API/$endpoint" \
    -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: 2023-06-01" \
    -H "anthropic-beta: $BETA" \
    -H "content-type: application/json" \
    -d "$data"
}

api_post() { api_call "POST" "$1" "$2"; }
api_get()  { api_call "GET"  "$1"; }

# ── Session event sturen ─────────────────────────────────────
send_task() {
  local session_id=$1 task=$2
  api_post "sessions/$session_id/events" \
    "{\"type\": \"user\", \"content\": $(echo "$task" | jq -Rs .)}"
}

# ── Agents aanmaken ──────────────────────────────────────────
create_agents() {
  head "Agents aanmaken"
  mkdir -p "$ARMY_DIR" "$LOG_DIR" "$TASK_DIR" "$REPORT_DIR"

  # ── SCOUT ─────────────────────────────────────────────────
  log "Scout agent aanmaken..."
  SCOUT=$(api_post "agents" "$(cat <<EOF
{
  "name": "${PROJECT_NAME}-scout",
  "model": "$MODEL",
  "system": "Jij bent de Scout van project '$PROJECT_NAME'. Stack: $TECH_STACK.\n\nJouw taak bij elke run:\n1. Lees alle bestanden in /workspace recursief\n2. Lees bestaande .army/reports/ als die er zijn\n3. Schrijf een scherp PROJECT_BRIEF.md naar /mnt/session/outputs/ met:\n   - Wat doet dit project?\n   - Wat is af?\n   - Wat is kapot of ontbreekt?\n   - Top 3 prioriteiten voor het team\n   - Welke agents er nodig zijn (builder/qa/deployer/specialist)\n4. Schrijf aparte taakbestanden naar /mnt/session/outputs/tasks/ per agent\n\nWerk autonoom en grondig. Geen vragen stellen.",
  "tools": [{"type": "agent_toolset_20260401"}]
}
EOF
)")
  SCOUT_ID=$(echo "$SCOUT" | jq -r '.id')
  ok "Scout: $SCOUT_ID"

  # ── ARCHITECT ─────────────────────────────────────────────
  log "Architect agent aanmaken..."
  ARCHITECT=$(api_post "agents" "$(cat <<EOF
{
  "name": "${PROJECT_NAME}-architect",
  "model": "$MODEL",
  "system": "Jij bent de Architect van project '$PROJECT_NAME'. Stack: $TECH_STACK.\n\nJouw taak:\n1. Lees /workspace/.army/reports/scout_brief.md\n2. Lees de huidige codebase structuur\n3. Ontwerp de implementatie voor de hoogste prioriteit\n4. Schrijf naar /mnt/session/outputs/:\n   - ARCHITECTURE.md: technisch ontwerp\n   - IMPLEMENTATION_PLAN.md: stap-voor-stap wat de Builder moet doen\n   - FILES_TO_CHANGE.md: exacte bestanden en wijzigingen\n\nWees specifiek en concreet. De Builder volgt jouw plan letterlijk.",
  "tools": [{"type": "agent_toolset_20260401"}]
}
EOF
)")
  ARCHITECT_ID=$(echo "$ARCHITECT" | jq -r '.id')
  ok "Architect: $ARCHITECT_ID"

  # ── BUILDER ───────────────────────────────────────────────
  log "Builder agent aanmaken..."
  BUILDER=$(api_post "agents" "$(cat <<EOF
{
  "name": "${PROJECT_NAME}-builder",
  "model": "$MODEL",
  "system": "Jij bent de Builder van project '$PROJECT_NAME'. Stack: $TECH_STACK.\n\nJouw taak:\n1. Lees /workspace/.army/reports/implementation_plan.md\n2. Implementeer ALLE stappen uit het plan\n3. Schrijf nette, gedocumenteerde code\n4. Zorg dat elke wijziging werkt voor je verder gaat\n5. Schrijf naar /mnt/session/outputs/:\n   - BUILD_REPORT.md: wat je hebt gebouwd\n   - CHANGED_FILES.md: lijst van gewijzigde bestanden\n6. Commit alles naar branch 'army/$(date +%Y%m%d)'\n\nCode schrijven is jouw enige doel. Geen halfwerk.",
  "tools": [{"type": "agent_toolset_20260401"}]
}
EOF
)")
  BUILDER_ID=$(echo "$BUILDER" | jq -r '.id')
  ok "Builder: $BUILDER_ID"

  # ── QA ────────────────────────────────────────────────────
  log "QA agent aanmaken..."
  QA=$(api_post "agents" "$(cat <<EOF
{
  "name": "${PROJECT_NAME}-qa",
  "model": "$MODEL",
  "system": "Jij bent de QA agent van project '$PROJECT_NAME'. Stack: $TECH_STACK.\n\nJouw taak:\n1. Lees /workspace/.army/reports/build_report.md\n2. Lees alle gewijzigde bestanden\n3. Schrijf en voer tests uit voor elke wijziging\n4. Controleer: werkt het? Zijn er edge cases? Zijn er bugs?\n5. Schrijf naar /mnt/session/outputs/:\n   - QA_REPORT.md met PASSED of FAILED + details\n   - BUGS_FOUND.md als er fouten zijn\n\nAls er bugs zijn: beschrijf ze exact zodat de Builder ze kan fixen.\nGoedkeuring gaat ALLEEN door als alles werkt.",
  "tools": [{"type": "agent_toolset_20260401"}]
}
EOF
)")
  QA_ID=$(echo "$QA" | jq -r '.id')
  ok "QA: $QA_ID"

  # ── DEPLOYER ──────────────────────────────────────────────
  log "Deployer agent aanmaken..."
  DEPLOYER=$(api_post "agents" "$(cat <<EOF
{
  "name": "${PROJECT_NAME}-deployer",
  "model": "$MODEL",
  "system": "Jij bent de Deployer van project '$PROJECT_NAME'.\n\nJouw taak:\n1. Check /workspace/.army/reports/qa_report.md — alleen deployen als PASSED\n2. Merge de army branch naar main\n3. Run deploy commando's uit package.json of Makefile\n4. Schrijf naar /mnt/session/outputs/:\n   - DEPLOY_REPORT.md: wat deployed is, wanneer, welke versie\n\nBij FAILED in QA: stop en schrijf DEPLOY_BLOCKED.md met reden.",
  "tools": [{"type": "agent_toolset_20260401"}]
}
EOF
)")
  DEPLOYER_ID=$(echo "$DEPLOYER" | jq -r '.id')
  ok "Deployer: $DEPLOYER_ID"

  # ── IMPROVER ──────────────────────────────────────────────
  log "Improver agent aanmaken..."
  IMPROVER=$(api_post "agents" "$(cat <<EOF
{
  "name": "${PROJECT_NAME}-improver",
  "model": "$MODEL",
  "system": "Jij bent de Improver van project '$PROJECT_NAME'.\n\nJouw taak (na elke deploy cyclus):\n1. Lees alle rapporten in /workspace/.army/reports/\n2. Analyseer: wat gaat goed? Wat duurt te lang? Wat faalt vaak?\n3. Verbeter de agent definities in /workspace/.army/agents/\n4. Voeg nieuwe gespecialiseerde agents toe als dat efficiënter is\n5. Schrijf verbeterde system prompts terug naar de configs\n6. Rapporteer wat je hebt veranderd naar /mnt/session/outputs/IMPROVEMENTS.md\n\nJij zorgt dat het team elke cyclus beter wordt.",
  "tools": [{"type": "agent_toolset_20260401"}]
}
EOF
)")
  IMPROVER_ID=$(echo "$IMPROVER" | jq -r '.id')
  ok "Improver: $IMPROVER_ID"

  # ── IDs opslaan ───────────────────────────────────────────
  cat > "$ENV_FILE" <<EOF
SCOUT_ID=$SCOUT_ID
ARCHITECT_ID=$ARCHITECT_ID
BUILDER_ID=$BUILDER_ID
QA_ID=$QA_ID
DEPLOYER_ID=$DEPLOYER_ID
IMPROVER_ID=$IMPROVER_ID
PROJECT_NAME=$PROJECT_NAME
PROJECT_DIR=$PROJECT_DIR
GITHUB_REMOTE=$GITHUB_REMOTE
EOF

  ok "Alle agent IDs opgeslagen in $ENV_FILE"
}

# ── Environment aanmaken ─────────────────────────────────────
create_environment() {
  head "Environment aanmaken"
  log "Cloud container opzetten..."

  ENV_PAYLOAD="{
    \"name\": \"${PROJECT_NAME}-env-$(date +%s)\",
    \"config\": {
      \"type\": \"cloud\",
      \"networking\": {\"type\": \"unrestricted\"},
      \"packages\": {
        \"pip\": [\"pytest\", \"requests\", \"pandas\"],
        \"npm\": [\"jest\", \"typescript\"]
      }
    }
  }"

  ENVIRONMENT=$(api_post "environments" "$ENV_PAYLOAD")
  ENV_ID=$(echo "$ENVIRONMENT" | jq -r '.id')

  echo "ENV_ID=$ENV_ID" >> "$ENV_FILE"
  ok "Environment: $ENV_ID"
}

# ── Sessie starten voor een agent ────────────────────────────
start_session() {
  local agent_id=$1 agent_name=$2
  log "Sessie starten voor $agent_name..."

  SESSION_PAYLOAD="{\"agent\": \"$agent_id\", \"environment_id\": \"$ENV_ID\""

  if [[ -n "${GITHUB_REMOTE:-}" && -n "${GITHUB_TOKEN:-}" ]]; then
    SESSION_PAYLOAD="$SESSION_PAYLOAD,
    \"resources\": [{
      \"type\": \"github_repository\",
      \"url\": \"$GITHUB_REMOTE\",
      \"authorization_token\": \"$GITHUB_TOKEN\",
      \"checkout\": {\"type\": \"branch\", \"name\": \"main\"}
    }]"
  fi

  SESSION_PAYLOAD="$SESSION_PAYLOAD}"

  SESSION=$(api_post "sessions" "$SESSION_PAYLOAD")
  echo "$SESSION" | jq -r '.id'
}

# ── Output files ophalen van een sessie ──────────────────────
fetch_outputs() {
  local session_id=$1 dest_dir=$2
  log "Outputs ophalen van sessie $session_id..."

  FILES=$(api_get "files?scope=$session_id" 2>/dev/null || echo '{"data":[]}')
  COUNT=$(echo "$FILES" | jq '.data | length')

  if [[ "$COUNT" -gt 0 ]]; then
    mkdir -p "$dest_dir"
    echo "$FILES" | jq -r '.data[] | "\(.id) \(.filename)"' | while read -r fid fname; do
      curl -sS "$API/files/$fid/content" \
        -H "x-api-key: $ANTHROPIC_API_KEY" \
        -H "anthropic-version: 2023-06-01" \
        -H "anthropic-beta: $BETA" \
        -o "$dest_dir/$fname"
      ok "Opgehaald: $fname"
    done
  fi
}

# ── Wachten tot sessie klaar is ──────────────────────────────
wait_for_session() {
  local session_id=$1 timeout=${2:-600}
  local elapsed=0
  log "Wachten op sessie $session_id..."

  while [[ $elapsed -lt $timeout ]]; do
    STATUS=$(api_get "sessions/$session_id" | jq -r '.status // "unknown"')
    case "$STATUS" in
      idle|completed) ok "Sessie klaar (status: $STATUS)"; return 0 ;;
      failed|error)   warn "Sessie gefaald (status: $STATUS)"; return 1 ;;
    esac
    sleep 10; elapsed=$((elapsed + 10))
    echo -n "."
  done
  warn "Timeout na ${timeout}s"
  return 1
}

# ── Eeen volledige bouw-cyclus ────────────────────────────────
run_cycle() {
  local cycle_num=$1
  head "Cyclus #$cycle_num — $(date '+%d %b %Y %H:%M')"
  source "$ENV_FILE"

  mkdir -p "$REPORT_DIR"
  CYCLE_LOG="$LOG_DIR/cycle-$cycle_num-$(date +%Y%m%d-%H%M%S).log"
  exec > >(tee -a "$CYCLE_LOG") 2>&1

  # ── 1. Scout ──────────────────────────────────────────────
  log "Scout aan het werk..."
  SCOUT_SESSION=$(start_session "$SCOUT_ID" "scout")
  send_task "$SCOUT_SESSION" "Analyseer het project volledig en schrijf de brief + takenverdeling."
  wait_for_session "$SCOUT_SESSION" 300 && \
    fetch_outputs "$SCOUT_SESSION" "$REPORT_DIR" || warn "Scout had problemen"

  # ── 2. Architect ──────────────────────────────────────────
  if [[ -f "$REPORT_DIR/PROJECT_BRIEF.md" ]]; then
    log "Architect aan het werk..."
    ARCH_SESSION=$(start_session "$ARCHITECT_ID" "architect")
    send_task "$ARCH_SESSION" "Lees de scout brief en ontwerp de implementatie voor prioriteit #1."
    wait_for_session "$ARCH_SESSION" 300 && \
      fetch_outputs "$ARCH_SESSION" "$REPORT_DIR" || warn "Architect had problemen"
  else
    warn "Geen scout brief gevonden, architect overgeslagen"
  fi

  # ── 3. Builder ────────────────────────────────────────────
  if [[ -f "$REPORT_DIR/IMPLEMENTATION_PLAN.md" ]]; then
    log "Builder aan het werk..."
    BUILD_SESSION=$(start_session "$BUILDER_ID" "builder")
    send_task "$BUILD_SESSION" "Implementeer het plan uit IMPLEMENTATION_PLAN.md volledig."
    wait_for_session "$BUILD_SESSION" 600 && \
      fetch_outputs "$BUILD_SESSION" "$REPORT_DIR" || warn "Builder had problemen"
  fi

  # ── 4. QA ─────────────────────────────────────────────────
  if [[ -f "$REPORT_DIR/BUILD_REPORT.md" ]]; then
    log "QA aan het werk..."
    QA_SESSION=$(start_session "$QA_ID" "qa")
    send_task "$QA_SESSION" "Test alles wat de Builder heeft gebouwd. Schrijf QA_REPORT.md."
    wait_for_session "$QA_SESSION" 300 && \
      fetch_outputs "$QA_SESSION" "$REPORT_DIR" || warn "QA had problemen"
  fi

  # ── 5. Deploy (alleen als QA passed) ──────────────────────
  if [[ -f "$REPORT_DIR/QA_REPORT.md" ]]; then
    if grep -qi "PASSED" "$REPORT_DIR/QA_REPORT.md"; then
      log "Deployer aan het werk..."
      DEPLOY_SESSION=$(start_session "$DEPLOYER_ID" "deployer")
      send_task "$DEPLOY_SESSION" "QA is PASSED. Deploy naar productie."
      wait_for_session "$DEPLOY_SESSION" 300 && \
        fetch_outputs "$DEPLOY_SESSION" "$REPORT_DIR" || warn "Deployer had problemen"
    else
      warn "QA FAILED — deploy overgeslagen"
      log "Builder gaat bugs fixen..."
      FIX_SESSION=$(start_session "$BUILDER_ID" "builder-fix")
      send_task "$FIX_SESSION" "Lees BUGS_FOUND.md en fix alle bugs. Commit de fixes."
      wait_for_session "$FIX_SESSION" 300
    fi
  fi

  # ── 6. Improver ───────────────────────────────────────────
  log "Improver analyseert de cyclus..."
  IMP_SESSION=$(start_session "$IMPROVER_ID" "improver")
  send_task "$IMP_SESSION" "Analyseer alle rapporten van cyclus #$cycle_num en verbeter het team."
  wait_for_session "$IMP_SESSION" 300 && \
    fetch_outputs "$IMP_SESSION" "$REPORT_DIR" || warn "Improver had problemen"

  ok "Cyclus #$cycle_num voltooid — volgende over ${LOOP_INTERVAL}s"
  echo ""
}

# ── Status weergeven ─────────────────────────────────────────
show_status() {
  head "Army Status"
  source "$ENV_FILE" 2>/dev/null || err "Geen .army/.env — run eerst: ./army.sh setup"
  echo -e "Project:    ${BOLD}$PROJECT_NAME${NC}"
  echo -e "Scout:      $SCOUT_ID"
  echo -e "Architect:  $ARCHITECT_ID"
  echo -e "Builder:    $BUILDER_ID"
  echo -e "QA:         $QA_ID"
  echo -e "Deployer:   $DEPLOYER_ID"
  echo -e "Improver:   $IMPROVER_ID"
  echo ""
  echo "Laatste rapporten:"
  ls -lt "$REPORT_DIR"/*.md 2>/dev/null | head -5 || echo "  Nog geen rapporten"
}

# ── Hoofdmenu ────────────────────────────────────────────────
main() {
  echo -e "${BOLD}${BLUE}"
  echo "  ╔═══════════════════════════════╗"
  echo "  ║   AGENT ARMY                  ║"
  echo "  ║   24/7 autonoom bouwen        ║"
  echo "  ╚═══════════════════════════════╝"
  echo -e "${NC}"

  COMMAND=${1:-"help"}

  case "$COMMAND" in
    setup)
      check_deps
      detect_project
      create_agents
      create_environment
      echo ""
      ok "Setup klaar! Start de army met: ./army.sh run"
      ;;

    run)
      check_deps
      detect_project
      [[ ! -f "$ENV_FILE" ]] && err "Eerst setup doen: ./army.sh setup"
      source "$ENV_FILE"
      log "Army gestart. Stop met Ctrl+C."
      CYCLE=1
      while true; do
        run_cycle $CYCLE
        CYCLE=$((CYCLE + 1))
        log "Volgende cyclus over ${LOOP_INTERVAL}s..."
        sleep $LOOP_INTERVAL
      done
      ;;

    once)
      check_deps
      detect_project
      [[ ! -f "$ENV_FILE" ]] && err "Eerst setup doen: ./army.sh setup"
      source "$ENV_FILE"
      run_cycle 1
      ;;

    status)
      show_status
      ;;

    reset)
      warn "Dit verwijdert alle army bestanden. Zeker weten? (j/n)"
      read -r confirm
      [[ "$confirm" == "j" ]] && rm -rf "$ARMY_DIR" && ok "Reset klaar" || log "Geannuleerd"
      ;;

    help|*)
      echo "Gebruik: ./army.sh [commando]"
      echo ""
      echo "  setup   — Agents + environment aanmaken (eeen keer)"
      echo "  run     — Army starten, loopt 24/7"
      echo "  once    — Eeen cyclus draaien"
      echo "  status  — Status + agent IDs bekijken"
      echo "  reset   — Alles wissen en opnieuw beginnen"
      echo ""
      echo "Vereisten:"
      echo "  export ANTHROPIC_API_KEY=sk-ant-..."
      echo "  export GITHUB_TOKEN=ghp_...  (optioneel, voor GitHub koppeling)"
      ;;
  esac
}

main "$@"
