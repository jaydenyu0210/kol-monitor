# KOL Monitor Pro Development Makefile

.PHONY: dev stop status logs-back logs-front clean

# 🚀 Start the full stack (Backend in Docker + Frontend locally)
dev:
	@echo "📦 Starting Backend (Docker)..."
	@docker compose up -d
	@echo "🌐 Starting Frontend (Next.js)..."
	@cd frontend-next && npm run dev

# 🛑 Stop everything
stop:
	@echo "🛑 Stopping Backend Docker container..."
	@docker compose down
	@echo "⚠️ Please stop the frontend manually (Ctrl+C) if it's running in your terminal."

# 📊 Check status of backend
status:
	@docker compose ps

# 📝 View backend logs
logs-back:
	@docker logs -f kol-monitor-backend

# 🧹 Clean up Docker images and containers
clean:
	@docker compose down --rmi local --volumes --remove-orphans
