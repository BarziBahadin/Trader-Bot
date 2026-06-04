package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"trader/internal/config"
	"trader/internal/db"
	"trader/internal/httpapi"
	"trader/internal/telegram"
	"trader/internal/worker"
)

func main() {
	settings := config.Load()
	store, err := db.Open(settings.DatabasePath)
	if err != nil {
		log.Fatalf("open database: %v", err)
	}
	defer store.Close()
	if err := store.Migrate(); err != nil {
		log.Fatalf("migrate database: %v", err)
	}
	if err := store.SeedDefaults(settings); err != nil {
		log.Fatalf("seed defaults: %v", err)
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if settings.AutoStartWorker {
		go worker.Run(ctx, settings, store)
	}
	if settings.AutoStartTelegram {
		go telegram.RunPolling(ctx, settings, store)
	}

	server := &http.Server{
		Addr:              ":8000",
		Handler:           httpapi.NewServer(settings, store),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownCtx)
	}()

	log.Printf("trader-api listening on %s", server.Addr)
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatalf("serve: %v", err)
	}
}
