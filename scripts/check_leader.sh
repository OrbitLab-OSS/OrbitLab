PATRONICTL="patronictl -c /etc/datacore/patroni.yaml"

if ! $PATRONICTL list | grep "$(hostname)" > /dev/null; then
    echo "DataCore node $(hostname) not in Patroni cluster."
    exit 1
fi
if ! su -c "psql -d postgres -Atqc 'SELECT 1;'" - postgres > /dev/null; then
    echo "Unable to connect to postgres."
    exit 1
fi
if [ "$($PATRONICTL list | grep "$(hostname)" | awk '{print $6}')" == "Leader" ]; then
    if [ "$(su -c "psql -d postgres -Atqc 'SELECT pg_is_in_recovery();'" - postgres)" != "f" ]; then
        echo "Leader is in recovery but it shouldn't be."
        exit 1
    fi
else
    if [ "$($PATRONICTL list | grep "$(hostname)" | awk '{print $8}')" != "streaming" ]; then
        CLUSTER=$($PATRONICTL list | grep "Cluster" | awk '{print $3}')
        $PATRONICTL reinit "$CLUSTER" "$(hostname)" --force --wait
        if [ "$($PATRONICTL list | grep "$(hostname)" | awk '{print $8}')" != "streaming" ]; then
            echo "Failed to reinit Replica node $(hostname)."
            exit 1
        fi
    fi
fi
