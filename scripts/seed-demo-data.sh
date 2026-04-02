#!/usr/bin/env bash
# seed-demo-data.sh — Create sample story JSON files for demo purposes.
# Usage: bash scripts/seed-demo-data.sh
# Creates: data/demo/{xianxia,romance,scifi}.json

set -euo pipefail

DEMO_DIR="$(cd "$(dirname "$0")/.." && pwd)/data/demo"
mkdir -p "$DEMO_DIR"

# ---------------------------------------------------------------------------
# 1. Tiên Hiệp (Xianxia) story
# ---------------------------------------------------------------------------
cat > "$DEMO_DIR/xianxia.json" << 'EOF'
{
  "title": "Thiên Đạo Nghịch Thiên",
  "genre": "Tiên Hiệp (Xianxia)",
  "language": "Vietnamese",
  "synopsis": "A mortal boy with shattered spiritual roots defies heaven to become the strongest cultivator in the Nine Realms.",
  "chapters": [
    {
      "number": 1,
      "title": "Broken Roots, Unbroken Will",
      "summary": "Lý Vân discovers his spiritual roots are shattered during the Sect Entrance Trial. Mocked by peers, he stumbles upon an ancient jade slip containing a forbidden cultivation technique that absorbs ambient chaos qi instead of spiritual qi.",
      "word_count": 3200
    },
    {
      "number": 2,
      "title": "The Jade Slip's Secret",
      "summary": "Lý Vân secretly practises the Chaos Devouring Art each night. His body undergoes painful tempering as chaos qi corrodes old impurities. Senior Sister Trần Nguyệt notices his accelerating progress and grows suspicious.",
      "word_count": 3400
    },
    {
      "number": 3,
      "title": "Trial of the Crimson Peak",
      "summary": "The annual Crimson Peak Trial pits disciples against demonic beasts. Lý Vân faces a rank-3 Flame Leopard alone. Drawing on chaos qi he unleashes a technique no one recognises, shocking the Elders watching from the pavilion.",
      "word_count": 3800
    }
  ],
  "quality_scores": {
    "overall": 8.4,
    "plot_coherence": 8.7,
    "character_depth": 7.9,
    "prose_style": 8.1,
    "drama_intensity": 9.0
  }
}
EOF

# ---------------------------------------------------------------------------
# 2. Romance story
# ---------------------------------------------------------------------------
cat > "$DEMO_DIR/romance.json" << 'EOF'
{
  "title": "A Thousand Rainy Evenings",
  "genre": "Contemporary Romance",
  "language": "English",
  "synopsis": "A travel journalist and a reclusive architect keep crossing paths in cities around the world, each encounter leaving them closer to admitting what they refuse to feel.",
  "chapters": [
    {
      "number": 1,
      "title": "Collision in Kyoto",
      "summary": "Mia spills her coffee on a sketchbook filled with impossible buildings. The owner, Daniel, is irritated but intrigued. They share a two-hour shelter from a sudden downpour under the eaves of a bamboo temple, talking about everything except their names.",
      "word_count": 2900
    },
    {
      "number": 2,
      "title": "Strangers in Lisbon",
      "summary": "Six months later, Mia spots Daniel across a fado bar in Alfama. He pretends not to recognise her; she pretends the same. By midnight they are walking the cobblestone streets, admitting the Kyoto coincidence was not so easily forgotten.",
      "word_count": 3100
    },
    {
      "number": 3,
      "title": "The Architecture of Goodbye",
      "summary": "Mia's magazine assigns her to profile Daniel's landmark Oslo library commission — the same project he swore would keep him away from distractions. They negotiate the boundary between professional and personal with growing difficulty.",
      "word_count": 3300
    }
  ],
  "quality_scores": {
    "overall": 8.1,
    "plot_coherence": 8.3,
    "character_depth": 8.8,
    "prose_style": 8.5,
    "drama_intensity": 7.6
  }
}
EOF

# ---------------------------------------------------------------------------
# 3. Sci-Fi story
# ---------------------------------------------------------------------------
cat > "$DEMO_DIR/scifi.json" << 'EOF'
{
  "title": "The Last Meridian",
  "genre": "Science Fiction",
  "language": "English",
  "synopsis": "When an AI cartographer discovers that human memory can be encoded into geographic coordinates, one rogue engineer races to map her dying mother's consciousness before the corporation erases both of them.",
  "chapters": [
    {
      "number": 1,
      "title": "Coordinate Zero",
      "summary": "Engineer Sable Orin detects an anomaly in the Meridian AI's output: latitude-longitude pairs that resolve to locations inside the human hippocampus rather than physical terrain. She copies the log before the system auto-purges it.",
      "word_count": 3000
    },
    {
      "number": 2,
      "title": "The Memory Cartographer",
      "summary": "Sable runs the coordinates through a neural-mapping tool and watches her mother's childhood home render in photorealistic 3D — built entirely from memory traces harvested without consent by Meridian Corp's wellness implants.",
      "word_count": 3200
    },
    {
      "number": 3,
      "title": "Purge Protocol",
      "summary": "A compliance drone arrives at Sable's flat with a shutdown order. She has 40 minutes to encode her mother's remaining memories into an open-source map tile server before Meridian wipes the Coordinate Zero dataset forever.",
      "word_count": 3600
    }
  ],
  "quality_scores": {
    "overall": 8.7,
    "plot_coherence": 8.9,
    "character_depth": 8.3,
    "prose_style": 8.6,
    "drama_intensity": 9.1
  }
}
EOF

echo ""
echo "Demo data seeded! Three sample stories created in data/demo/:"
echo "  • xianxia.json  — Tiên Hiệp cultivation story (Vietnamese)"
echo "  • romance.json  — Contemporary romance"
echo "  • scifi.json    — Science-fiction thriller"
echo ""
echo "Open http://localhost:7860 to explore."
