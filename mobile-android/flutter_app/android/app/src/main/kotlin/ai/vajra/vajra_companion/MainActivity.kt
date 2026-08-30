package ai.vajra.vajra_companion

import android.app.Activity
import android.content.Intent
import android.net.Uri
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Minimal Storage Access Framework bridge for "Files on this device" mode.
 * ACTION_OPEN_DOCUMENT / ACTION_CREATE_DOCUMENT surface internal storage, the
 * SD card, Google Drive and a plugged-in USB drive uniformly - no extra plugin.
 */
class MainActivity : FlutterActivity() {
    private val channel = "vajra/files"
    private val reqOpen = 8021
    private val reqSave = 8022
    private var pending: MethodChannel.Result? = null
    private var pendingSaveBytes: ByteArray? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channel).setMethodCallHandler { call, result ->
            when (call.method) {
                "openFiles" -> {
                    pending = result
                    val i = Intent(Intent.ACTION_OPEN_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "*/*"
                        putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
                    }
                    startActivityForResult(i, reqOpen)
                }
                "saveFile" -> {
                    pending = result
                    pendingSaveBytes = call.argument<ByteArray>("bytes")
                    val name = call.argument<String>("name") ?: "file.txt"
                    val i = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
                        addCategory(Intent.CATEGORY_OPENABLE)
                        type = "application/octet-stream"
                        putExtra(Intent.EXTRA_TITLE, name)
                    }
                    startActivityForResult(i, reqSave)
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val res = pending ?: return
        pending = null
        if (resultCode != Activity.RESULT_OK || data == null) {
            res.success(null)
            pendingSaveBytes = null
            return
        }
        try {
            when (requestCode) {
                reqOpen -> {
                    val uris = mutableListOf<Uri>()
                    data.clipData?.let { for (n in 0 until it.itemCount) uris.add(it.getItemAt(n).uri) }
                    data.data?.let { uris.add(it) }
                    val out = ArrayList<HashMap<String, String>>()
                    for (u in uris) {
                        val bytes = contentResolver.openInputStream(u)?.use { it.readBytes() } ?: continue
                        out.add(hashMapOf(
                            "name" to displayName(u),
                            "content" to String(bytes, Charsets.UTF_8),
                        ))
                    }
                    res.success(out)
                }
                reqSave -> {
                    val bytes = pendingSaveBytes ?: ByteArray(0)
                    pendingSaveBytes = null
                    contentResolver.openOutputStream(data.data!!, "wt")?.use { it.write(bytes) }
                    res.success(displayName(data.data!!))
                }
            }
        } catch (e: Exception) {
            res.error("io", e.message, null)
        }
    }

    private fun displayName(uri: Uri): String {
        contentResolver.query(uri, null, null, null, null)?.use { c ->
            val idx = c.getColumnIndex("_display_name")
            if (idx >= 0 && c.moveToFirst()) return c.getString(idx)
        }
        return uri.lastPathSegment?.substringAfterLast('/') ?: "file"
    }
}
