package dev.ragger.plugin.scripting;

import net.runelite.api.Client;
import net.runelite.api.EquipmentInventorySlot;
import net.runelite.api.Item;
import net.runelite.api.ItemComposition;
import net.runelite.api.ItemContainer;
import net.runelite.api.gameval.InventoryID;
import net.runelite.client.game.ItemManager;
import party.iroiro.luajava.Lua;

/**
 * Lua binding for player inventory and equipment.
 * Exposed as the global "inventory" table in Lua scripts.
 */
public class InventoryApi {

    private final Client client;
    private final ItemManager itemManager;

    public InventoryApi(final Client client, final ItemManager itemManager) {
        this.client = client;
        this.itemManager = itemManager;
    }

    public void register(final Lua lua) {
        lua.createTable(0, 4);

        lua.push(this::items);
        lua.setField(-2, "items");

        lua.push(this::equipment);
        lua.setField(-2, "equipment");

        lua.push(this::contains);
        lua.setField(-2, "contains");

        lua.push(this::count);
        lua.setField(-2, "count");

        lua.setGlobal("inventory");
    }

    /**
     * inventory:items() -> array of {id, name, quantity, slot}
     * Returns all non-empty inventory slots.
     */
    private int items(final Lua lua) {
        lua.createTable(0, 0);

        final ItemContainer container = client.getItemContainer(InventoryID.INV);
        if (container == null) {
            return 1;
        }

        final Item[] allItems = container.getItems();
        int index = 1;

        for (int slot = 0; slot < allItems.length; slot++) {
            final Item item = allItems[slot];
            if (item.getId() == -1 || item.getQuantity() == 0) {
                continue;
            }

            lua.createTable(0, 4);

            lua.push(item.getId());
            lua.setField(-2, "id");

            final ItemComposition comp = itemManager.getItemComposition(item.getId());
            lua.push(comp.getName());
            lua.setField(-2, "name");

            lua.push(item.getQuantity());
            lua.setField(-2, "quantity");

            lua.push(slot);
            lua.setField(-2, "slot");

            lua.rawSetI(-2, index++);
        }

        return 1;
    }

    /**
     * inventory:equipment() -> array of {id, name, quantity, slot, slot_name}
     * Returns all equipped items.
     */
    private int equipment(final Lua lua) {
        lua.createTable(0, 0);

        final ItemContainer container = client.getItemContainer(InventoryID.WORN);
        if (container == null) {
            return 1;
        }

        final Item[] allItems = container.getItems();
        int index = 1;

        for (final EquipmentInventorySlot eqSlot : EquipmentInventorySlot.values()) {
            final int slotIdx = eqSlot.getSlotIdx();
            if (slotIdx >= allItems.length) {
                continue;
            }

            final Item item = allItems[slotIdx];
            if (item.getId() == -1 || item.getQuantity() == 0) {
                continue;
            }

            lua.createTable(0, 5);

            lua.push(item.getId());
            lua.setField(-2, "id");

            final ItemComposition comp = itemManager.getItemComposition(item.getId());
            lua.push(comp.getName());
            lua.setField(-2, "name");

            lua.push(item.getQuantity());
            lua.setField(-2, "quantity");

            lua.push(slotIdx);
            lua.setField(-2, "slot");

            lua.push(eqSlot.name().toLowerCase());
            lua.setField(-2, "slot_name");

            lua.rawSetI(-2, index++);
        }

        return 1;
    }

    /**
     * inventory:contains(itemId) -> bool
     */
    private int contains(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemContainer container = client.getItemContainer(InventoryID.INV);
        lua.push(container != null && container.contains(id));
        return 1;
    }

    /**
     * inventory:count(itemId) -> int
     */
    private int count(final Lua lua) {
        final int id = (int) lua.toInteger(2);
        final ItemContainer container = client.getItemContainer(InventoryID.INV);
        lua.push(container != null ? container.count(id) : 0);
        return 1;
    }
}
