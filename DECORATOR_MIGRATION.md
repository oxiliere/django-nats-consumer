# Migration vers l'approche avec décorateurs

## ⚠️ IMPORTANT : Convention de nommage des subjects

**FORTEMENT RECOMMANDÉ : Utilisez TOUJOURS la notation avec points (dot notation)**

```python
# ✅ RECOMMANDÉ : Notation avec points
'orders.created'
'users.profile.updated'
'payments.completed'

# ❌ DÉCONSEILLÉ : Autres séparateurs
'orders-created'      # Tirets
'orders_created'      # Underscores
'orderscreated'       # Sans séparateur
```

**Pourquoi la notation avec points ?**
- ✅ **Convention standard NATS** - Bonne pratique de l'industrie
- ✅ **Support des wildcards** - Fonctionne parfaitement avec `*` et `>`
- ✅ **Clarté hiérarchique** - Structure claire domaine.entité.action
- ✅ **Meilleur routage** - Plus facile de filtrer et router les messages
- ✅ **Cohérence** - Correspond aux patterns de l'écosystème NATS

## 🎯 Nouvelle approche avec `@handle`

La classe `ConsumerHandler` utilise maintenant des décorateurs pour enregistrer les handlers au lieu de la détection automatique basée sur les noms de méthodes.

### ✅ Avantages

- **Explicite** : Clair quelles méthodes gèrent quels subjects
- **Flexible** : Une méthode peut gérer plusieurs subjects
- **Wildcards** : Support complet des patterns `*` et `>`
- **Noms libres** : Les noms de méthodes peuvent être n'importe quoi

### 📝 Exemple de migration

#### Avant (détection automatique)

```python
from nats_consumer import ConsumerHandler

class OrderHandler(ConsumerHandler):
    def __init__(self):
        # ⚠️ ANCIEN CODE avec séparateurs mixtes (à éviter)
        subjects = [
            "orders.created",    # ✅ Bon
            "orders-updated",    # ❌ Mauvais (tirets)
            "orders_deleted"     # ❌ Mauvais (underscores)
        ]
        super().__init__(subjects)
    
    async def handle_created(self, msg):
        # Gérer orders.created
        pass
    
    async def handle_updated(self, msg):
        # Gérer orders-updated
        pass
    
    async def handle_deleted(self, msg):
        # Gérer orders_deleted
        pass
```

#### Après (avec décorateurs + notation correcte)

```python
from nats_consumer import ConsumerHandler, handle

class OrderHandler(ConsumerHandler):
    # ✅ NOUVEAU : Utiliser UNIQUEMENT la notation avec points
    @handle('orders.created')
    async def on_order_created(self, msg):
        # Gérer orders.created
        pass
    
    @handle('orders.updated')  # ✅ Corrigé : points au lieu de tirets
    async def on_order_updated(self, msg):
        # Gérer orders.updated
        pass
    
    @handle('orders.deleted')  # ✅ Corrigé : points au lieu d'underscores
    async def on_order_deleted(self, msg):
        # Gérer orders.deleted
        pass
    
    @handle('orders.*')  # ✅ Wildcard fonctionne parfaitement avec les points
    async def on_any_order(self, msg):
        # Catch-all pour tous les events orders
        pass
```

**⚠️ Note importante sur la migration :**

Si votre ancien code utilisait des tirets ou underscores, vous devez :
1. **Mettre à jour vos publishers** pour utiliser la notation avec points
2. **Mettre à jour vos streams** avec les nouveaux subjects
3. **Mettre à jour vos handlers** avec les décorateurs et les bons subjects

```python
# Migration des publishers
# AVANT
await js.publish("orders-created", data)  # ❌
await js.publish("orders_updated", data)  # ❌

# APRÈS
await js.publish("orders.created", data)  # ✅
await js.publish("orders.updated", data)  # ✅
```

### 🌟 Nouvelles fonctionnalités

#### 1. Un handler pour plusieurs subjects

```python
# ✅ Tous les subjects utilisent la notation avec points
@handle('users.created', 'users.registered', 'users.signup')
async def on_new_user(self, msg):
    # Une seule méthode pour 3 subjects différents
    pass
```

#### 2. Support des wildcards

```python
# ✅ Wildcards fonctionnent parfaitement avec la notation avec points
@handle('orders.*')
async def on_any_order_event(self, msg):
    # Match: orders.created, orders.updated, orders.deleted, etc.
    pass

@handle('notifications.>')
async def on_any_notification(self, msg):
    # Match: notifications.email, notifications.sms.sent, etc.
    pass

# ✅ Wildcards avancés
@handle('*.error')  # Match tous les domaines avec .error
async def on_any_error(self, msg):
    # Match: orders.error, users.error, payments.error
    pass
```

#### 3. Noms de méthodes libres

```python
@handle('orders.created')
async def process_new_order(self, msg):  # Nom explicite
    pass

@handle('orders.deleted')
async def cleanup_order(self, msg):  # Nom descriptif
    pass
```

### 🔧 Utilisation dans les consumers

Aucun changement dans l'utilisation :

```python
class OrderConsumer(JetstreamPushConsumer):
    stream_name = "orders"
    # ✅ TOUJOURS utiliser la notation avec points
    subjects = ["orders.created", "orders.updated", "orders.deleted"]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.handler = OrderHandler()
    
    async def handle_message(self, message):
        await self.handler.handle(message)
```

### 📊 Méthodes utilitaires

```python
handler = OrderHandler()

# Obtenir tous les subjects enregistrés
subjects = handler.get_subjects()
# ['orders.created', 'orders.updated', 'orders.*']  # ✅ Tous avec points

# Obtenir tous les noms de méthodes
methods = handler.get_handler_methods()
# ['on_order_created', 'on_order_updated', 'on_any_order']
```

## 🎯 Exemples de patterns de subjects recommandés

```python
# Pattern 1 : domaine.action (simple)
'orders.created'
'payments.completed'
'users.registered'

# Pattern 2 : domaine.entité.action (détaillé)
'orders.payment.completed'
'users.profile.updated'
'notifications.email.sent'

# Pattern 3 : domaine.sous-domaine.entité.action (complexe)
'ecommerce.orders.payment.completed'
'platform.users.profile.updated'
'system.notifications.email.sent'

# ❌ À ÉVITER
'orders-created'        # Tirets
'orders_created'        # Underscores
'OrdersCreated'         # PascalCase
'ORDERS.CREATED'        # Majuscules
'orders created'        # Espaces
```

### ⚠️ Notes importantes

1. **Plus besoin de `__init__`** : Les subjects sont détectés automatiquement via les décorateurs
2. **Plus de conventions de nommage** : Les méthodes peuvent avoir n'importe quel nom
3. **Wildcards supportés** : `*` et `>` fonctionnent maintenant
4. **Fallback automatique** : Les messages non gérés appellent `fallback_handle()` qui NAK par défaut
5. **⚠️ UTILISEZ TOUJOURS LA NOTATION AVEC POINTS** : `orders.created` et non `orders-created` ou `orders_created`

### 🐛 Correction du double acquittement

Le nouveau système vérifie automatiquement si un message a déjà été acquitté (par `fallback_handle` par exemple) avant de tenter un nouvel acquittement, évitant l'erreur `nats: message was already acknowledged`.

## 📋 Checklist de migration

- [ ] Remplacer tous les subjects avec tirets/underscores par la notation avec points
- [ ] Ajouter `from nats_consumer import handle` dans vos imports
- [ ] Ajouter le décorateur `@handle()` sur toutes les méthodes de handler
- [ ] Supprimer le `__init__` qui passait les subjects (si présent)
- [ ] Mettre à jour vos publishers pour utiliser les nouveaux subjects
- [ ] Mettre à jour vos streams NATS avec les nouveaux subjects
- [ ] Tester que tous les messages sont bien routés
- [ ] Vérifier les logs pour les warnings de collision de subjects
