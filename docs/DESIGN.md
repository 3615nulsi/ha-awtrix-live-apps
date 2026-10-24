# Awtrix Studio — note de conception

> Statut : brouillon à valider (v0.2, 24 octobre 2026)

## 1. Le problème

Aujourd'hui, pour afficher une donnée de Home Assistant sur une horloge AWTRIX 3,
on écrit une automatisation qui publie un JSON en MQTT, souvent sur un déclencheur
périodique (`time_pattern`). C'est la méthode des blueprints les plus utilisés,
et les intégrations AWTRIX existantes ne font qu'exposer un service « pousser une
app » qu'il faut toujours appeler depuis une automatisation.

Conséquences, vécues en vrai :

- chaque exécution écrit une ligne d'état pour l'automatisation, un événement
  `automation_triggered` et un `call_service` par publication, avec le payload
  complet : une app qui alterne deux pages toutes les 1,5 s produit
  ~30 000 exécutions et ~60 000 événements par jour, et fait gonfler la base
  du recorder de plusieurs centaines de Mo ;
- on republie même quand rien n'a changé ;
- l'alternance de pages se code à la main avec des `repeat` et des `delay` ;
- au redémarrage de l'horloge, les apps disparaissent jusqu'à la prochaine
  exécution.

## 2. L'idée

Une intégration où l'on **déclare** une app une fois, et qui la fait vivre toute
seule :

- un **modèle Jinja** produit le JSON AWTRIX de l'app ;
- l'intégration repère les entités utilisées dans le modèle et **ne republie que
  quand le rendu change** ;
- si le modèle renvoie une **liste**, chaque élément est une **page**, et
  l'intégration les fait alterner en interne ;
- **aucune automatisation, aucun appel de service, aucun événement enregistré.**

## 3. Principes

1. **Zéro bruit dans le recorder.** Aucune entité dont l'état change à chaque
   rendu ou à chaque page. Les publications passent par l'API Python MQTT de
   Home Assistant (`mqtt.async_publish`), qui ne génère pas d'événement
   `call_service`.
2. **Publier seulement ce qui change.** Chaque payload publié est mémorisé ; un
   rendu identique n'est pas republié.
3. **Le JSON AWTRIX tel quel.** Pas de surcouche maison : le modèle produit
   exactement le payload documenté par AWTRIX 3 (`text`, `draw`, `icon`,
   `blinkText`, etc.). Toute nouveauté du firmware est utilisable sans mise à
   jour de l'intégration.
4. **Compatible avec l'existant.** On ne touche qu'aux topics des apps que l'on gère.
   L'intégration cohabite avec la découverte MQTT native d'AWTRIX, les
   blueprints et les autres intégrations.

## 4. Firmwares supportés : AWTRIX 3 et AWTRIX NG

AWTRIX NG est une réécriture complète d'AWTRIX 3 par le même auteur, avec sa
propre API (« v1 ») : rien n'est compatible entre les deux, ni les topics ni le
format des payloads. Exemples :

| | AWTRIX 3 | AWTRIX NG |
|---|---|---|
| Publier une app | `<préfixe>/custom/<app>` | `<préfixe>/cmd/apps/pushed/<app>` |
| Couleur du texte | `color: "#FF0000"` | `textColor: [255, 0, 0]` |
| Durée de vie | `lifetime` (s) | `lifetimeMs` + `lifetimeExpiry` |

L'intégration gère les deux grâce à une couche « pilote » par firmware, choisie
à l'ajout de l'horloge (détection automatique si possible). Le pilote ne
s'occupe que du **transport** :

- topic de publication et de suppression d'une app ;
- topic qui indique l'app affichée (alternance « seulement à l'écran ») ;
- détection du redémarrage de l'horloge ;
- nom du champ de durée de vie quand l'option est activée.

Le **contenu** reste le JSON natif du firmware, écrit dans le modèle (principe
n° 3) : un modèle AWTRIX 3 ne s'affiche pas tel quel sur NG, il faut l'écrire
avec les champs NG. La documentation fournira chaque exemple dans les deux
formats.

À confirmer pendant le développement, dans la documentation NG : le topic de
l'app affichée, la suppression d'une app poussée, et le support des primitives
de dessin (pixels, lignes) dans les apps poussées.

## 5. Configuration (interface uniquement)

### 5.1 Une entrée par horloge

Ajout via *Paramètres → Appareils et services → Ajouter une intégration →
Awtrix Studio* :

| Champ | Exemple | Rôle |
|---|---|---|
| Firmware | AWTRIX 3 | AWTRIX 3 ou AWTRIX NG (§ 4), détecté si possible |
| Préfixe MQTT | `awtrix_1f1b94` | Préfixe des topics de l'horloge |

L'intégration vérifie que l'horloge répond (topic de statut du firmware) et
propose les préfixes déjà vus en découverte MQTT quand c'est possible.

### 5.2 Une sous-entrée par app

Chaque app est une **sous-entrée** de l'horloge (mécanisme natif des config
subentries de HA), ajoutée par un bouton « Ajouter une app » sur la carte de
l'intégration :

| Champ | Défaut | Rôle |
|---|---|---|
| Nom de l'app | — | Nom AWTRIX, ex. `tram` → topic `<préfixe>/custom/tram` (AWTRIX 3) |
| Modèle | — | Modèle Jinja (éditeur de code) qui rend un objet JSON (1 page) ou une liste d'objets (plusieurs pages) |
| Intervalle entre pages | 1,5 s | Durée d'affichage de chaque page |
| Alterner seulement à l'écran | oui | Voir § 6.3 |
| Masquer si vide | oui | Si toutes les pages sont vides (`{}`), l'app est retirée de la rotation |
| Durée de vie (`lifetime`) | désactivée | Si activée, l'horloge retire l'app quand Home Assistant ne la rafraîchit plus (HA arrêté). L'intégration entretient alors l'app automatiquement |

## 6. Fonctionnement

### 6.1 Rendu

- Le modèle est suivi avec `async_track_template_result` : HA nous rappelle dès
  qu'une entité utilisée change, et seulement si le **résultat** change.
- Le résultat est analysé comme du JSON :
  - un objet → une page ;
  - une liste → plusieurs pages ; les pages vides (`{}`) sont ignorées ;
  - JSON invalide → l'erreur est journalisée (une fois, pas en boucle) et la
    dernière version valide reste affichée.
- Un limiteur évite les rafales (au plus une publication par seconde et par app
  pour les changements de données ; l'alternance de pages suit son propre
  rythme).

### 6.2 Publication

- Topic fourni par le pilote du firmware (§ 4), QoS 0, sans `retain`.
- App masquée → suppression selon le firmware (payload vide sur AWTRIX 3).
- On ne publie jamais deux fois de suite le même payload.

### 6.3 Alternance de pages

- Le firmware publie le nom de l'app affichée (sur AWTRIX 3 : `<préfixe>/stats/currentApp`).
- Avec « alterner seulement à l'écran » (défaut) :
  - quand l'app n'est pas à l'écran, seule la **page 1** est publiée, et
    seulement quand elle change ;
  - quand l'app arrive à l'écran, l'intégration fait défiler les pages à
    l'intervalle choisi ;
  - quand elle quitte l'écran, on revient à la page 1 pour le prochain passage.
- Effet sur l'app tram : environ 7 publications par minute au lieu de 40, et
  aucune la nuit si l'app est masquée faute de passages.

### 6.4 Robustesse

- **Redémarrage de l'horloge** : détecté via le topic de statut du firmware (uptime qui
  repart à zéro) → toutes les apps sont republiées.
- **Redémarrage de HA** : les apps sont republiées au démarrage.
- **Suppression d'une app** dans l'interface → l'app est supprimée de
  l'horloge.

## 7. Entités et services

Volontairement minimalistes (principe n° 1) :

- par app, un **interrupteur** « Activée » : l'éteindre retire l'app de
  l'horloge sans perdre sa configuration ;
- service `awtrix_studio.refresh` : force la republication (une app ou toutes).

Pas de capteur « page courante » ni « dernier envoi » : ils écriraient dans la
base à chaque page, exactement ce qu'on cherche à éviter.

## 8. Exemple : l'app tram

Modèle (simplifié) — une liste de deux pages, le prochain passage puis le suivant :

```jinja
{% set s = 'sensor.via_domitia_tram_2_prochain_passage' %}
{% set deps = state_attr(s, 'departures') or [] %}
{% set pages = [] %}
{% for d in deps[:2] %}
  {% set pages = pages + [{
      "text": d.minutes ~ " min",
      "center": true,
      "icon": "tram"
  }] %}
{% endfor %}
{{ pages | tojson }}
```

Intervalle 1,5 s, alternance seulement à l'écran, masquer si vide.
Résultat : l'automatisation actuelle (déclencheur toutes les 3 s, `repeat`,
`delay`) disparaît entièrement.

## 9. Hors périmètre de la v1

- Transport HTTP (sans MQTT).
- Notifications AWTRIX (`<préfixe>/notify`).
- Aperçu en direct du rendu dans l'écran de configuration.
- Réglages globaux de l'horloge (luminosité, transitions) : déjà couverts par
  la découverte MQTT native et les autres intégrations.

## 10. Aspects techniques

- Domaine : `awtrix_studio`, dépendance : `mqtt`.
- Version minimale de HA : celle qui stabilise les config subentries (à
  confirmer, 2025.x).
- Distribution : HACS (`hacs.json`), validation GitHub Actions (hassfest +
  action HACS).
- Tests : `pytest-homeassistant-custom-component`, MQTT simulé.
- Traductions : anglais et français.
- Documentation (README) en anglais, avec l'app tram en exemple.
