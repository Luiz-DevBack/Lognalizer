document.addEventListener("DOMContentLoaded", () => {
    console.log("Magiccomp Log Analyzer • dashboard analítica carregada");

    // Se Chart.js não estiver disponível (deu ruim na CDN), sai fora
    if (typeof Chart === "undefined") {
        console.warn("Chart.js não carregado. Gráficos desativados.");
        return;
    }

    // Gráfico de tendência de erros (por enquanto, dados mockados)
    const ctxErrors = document.getElementById("chartErrorsTimeline");
    if (ctxErrors) {
        new Chart(ctxErrors, {
            type: "line",
            data: {
                labels: ["01h", "02h", "03h", "04h", "05h", "06h"],
                datasets: [
                    {
                        label: "ERROR",
                        data: [5, 9, 3, 10, 7, 4],
                        borderWidth: 2,
                        fill: false,
                    },
                    {
                        label: "WARNING",
                        data: [2, 3, 1, 4, 2, 1],
                        borderWidth: 2,
                        borderDash: [4, 4],
                        fill: false,
                    }
                ]
            },
            options: {
                plugins: {
                    legend: {
                        labels: {
                            color: "#e5e7eb",
                            usePointStyle: true
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: "#9ca3af" },
                        grid: { display: false }
                    },
                    y: {
                        ticks: { color: "#9ca3af" },
                        grid: { color: "rgba(55,65,81,0.4)" }
                    }
                }
            }
        });
    }

    const ctxHosts = document.getElementById("chartTopHosts");
    if (ctxHosts) {
        new Chart(ctxHosts, {
            type: "bar",
            data: {
                labels: ["srv-db01", "srv-web01", "proxy01", "zbx-server"],
                datasets: [
                    {
                        label: "Eventos ERROR",
                        data: [120, 80, 64, 32],
                        borderWidth: 1
                    }
                ]
            },
            options: {
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        ticks: { color: "#9ca3af" },
                        grid: { display: false }
                    },
                    y: {
                        ticks: { color: "#9ca3af" },
                        grid: { color: "rgba(55,65,81,0.4)" }
                    }
                }
            }
        });
    }

    // Depois a gente troca esses dados mock por /api/alguma-coisa
});
