# Optymalizacja Routingu w Sieci SDN

Projekt implementuje algorytm optymalizacji routingu w sieci SDN (Software-Defined Networking), którego celem jest dynamiczny dobór tras przepływów na podstawie aktualnego stanu sieci

## Cel projektu

- monitorowanie aktualnych przepustowości łączy w sieci,
- budowa tablicy stanu sieci na podstawie cyklicznych pomiarów,
- dynamiczny dobór tras dla nowych przepływów,
- minimalizacja przeciążeń i opóźnień,
- centralne sterowanie ruchem przez kontroler SDN.

## Wizualizacja sposobu działania algorytmu

![Pseudokod algorytmu routingu](images/SSP-pseudocode.drawio(2).png)

## Koncepcja działania algorytmu

1. Kontroler cyklicznie (co 1 s) zbiera statystyki portów przełączników i oblicza aktualną przepustowość łączy.
2. Na podstawie obciążenia łączy wyznaczane jest opóźnienie każdej krawędzi z wykorzystaniem modelu kolejki M/M/1/K.
3. Po odebraniu pakietu IPv4 kontroler uruchamia algorytm Dijkstry w celu wyznaczenia ścieżki o minimalnym łącznym opóźnieniu.
4. Dzięki okresowej aktualizacji metryk oraz ograniczonemu czasowi życia reguł przepływu, routing dynamicznie adaptuje się do aktualnego stanu sieci.

## Architektura systemu

- **Ryu** – kontroler SDN realizujący logikę sterowania siecią i komunikację OpenFlow,
- **Mininet** – emulator topologii sieciowej (hosty + przełączniki OpenFlow),
- **OpenFlow** – protokół komunikacji pomiędzy kontrolerem a przełącznikami,
- **Docker Compose** – uruchamianie i izolacja środowiska testowego,
  - kontener Ryu – IP: `172.16.0.2`
  - kontener Mininet – IP: `172.16.0.3`

---

# How to Run It

1. Install Docker.
2. Clone the repository:

```bash
git clone https://github.com/Widniw/ssp-project/
```

3. Build the Ryu image:

```bash
docker build --rm -f Dockerfile -t ryu-debian:latest .
```

4. Start the containers with Docker Compose:

```bash
docker compose up
```

---

# How to Stop Running Containers

1. Press `Ctrl + C` in the terminal running Docker Compose.
2. Remove the containers and network:

```bash
docker compose down
```

test
