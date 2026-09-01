# Getting a device's local key

Tuya's local protocol encrypts every packet with a **per-device local key**
(16 bytes, shown as a 16–24 character string). This integration never contacts
Tuya's cloud *at run time*, so you provide the key once, up front.

> The device id (`gwId`, 22 characters) is broadcast in the clear and is filled
> in automatically by discovery. Only the key must be supplied.

## 1. You already have it

If you previously used **LocalTuya**, **tinytuya**, `tuya-cli`, or Tuya's own
developer tools, the key is in:

* `tinytuya` → `devices.json` / `tuya-raw.json` (`"key"` field)
* LocalTuya → `.storage/core.config_entries` (`local_key`)
* `tuya-cli wizard` output

## 2. Tuya IoT Platform — one-time read of your own account (recommended)

This is the least effort and works for practically every device. It is the
**only** step that contacts a Tuya server, it reads only *your* devices, and you
never repeat it — afterwards the integration is fully local.

1. Go to <https://iot.tuya.com> → sign up / log in.
2. **Cloud → Development → Create Cloud Project**
   * Development Method: **Smart Home**
   * Data Center: the region your Smart Life app uses
     (Europe → `Central Europe`, most of the world outside CN/US → `Central
     Europe` or `Western Europe`; check the app: *Me → Settings → account →
     data center*).
3. After creation you land on **Project → Overview** — copy **Access ID/Client
   ID** and **Access Secret/Client Secret**.
4. **Project → Devices → Link App Account → Add App Account** → scan the QR with
   the Smart Life / Tuya app (*Me* tab → scan icon, top-right). Your devices
   appear under *Devices → All Devices*.
5. **Project → Service API → Go to Authorize** — make sure **IoT Core** is in
   the authorized list (add it if not).
6. Run the bundled helper (needs only Python, no extra packages):

   ```bash
   python tools/tuya_lan_cloud_keys.py --region eu \
       --client-id <Access ID> --client-secret <Access Secret>
   ```

   Region codes: `us eu cn in us-e eu-w sg` (match your project's data center).
   It prints a table of `name / device_id / local_key / ip / product_id`.

If you get `1106 permission deny` wait ~5 min after step 5 (authorization
propagation) and retry. `1004 sign invalid` → wrong secret or wrong region.

## 3. From an Android backup of the Smart Life / Tuya app (no root)

1. Pair the device normally with the app once (this is the only time the app
   talks to the cloud; you can put the phone in airplane mode afterwards).
2. `adb backup -f smartlife.ab -noapk com.tuya.smartlife`
   (or `com.thingclips.smartlife`, or the vendor-branded package).
3. Unpack: `dd if=smartlife.ab bs=1 skip=24 | zlib-flate -uncompress | tar -xvf -`
   (or use `android-backup-extractor`).
4. Look in `apps/<pkg>/sp/` and `apps/<pkg>/f/` — the `local_key` values are in
   the cached device list JSON.
5. `tools/tuya_lan_probe.py extract-keys <unpacked-dir>` will scan for them.

## 4. From a packet capture during pairing

The key is delivered to the device over the LAN during activation. Capture the
device's traffic (e.g. `tcpdump` on your router, or a mitmproxy on the phone
with the Tuya cert pinning bypassed) while pairing, and extract `localKey` from
the activation response.

## 5. cloudcutter (fully local, exploits older firmware)

<https://github.com/tuya-cloudcutter/tuya-cloudcutter> puts a device into a mode
where it hands you its config — including the key — without any cloud, and can
optionally flash open firmware (ESPHome / OpenBeken). Best when you want to keep
the device permanently off Tuya's servers.

## 6. Devices still on the default key

Some very old firmware (protocol 3.1) accepts the well-known default key while in
AP/pairing mode. Discovery tries this automatically and will mark such a device
as "no key needed".

---

Once you have the key, add the integration, pick the discovered device, and
paste the key into the **Local key** field.
