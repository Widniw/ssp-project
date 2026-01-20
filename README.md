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

Docker Compose runs two containers:

- **Ryu** – IP: `172.16.0.2`
- **Mininet** – IP: `172.16.0.3`

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
