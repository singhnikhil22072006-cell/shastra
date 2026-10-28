/** Plain-language copy. Verdict logic itself lives in the backend; this only explains it. */
export const VERDICT_PLAIN = {
  VERIFIED: "The issuer's registry record matches this letter field by field, and at least one independent signal (file fingerprint, intact signature, expected watermark or official-domain QR) supports it. It is still a decision-support result, not a legal determination.",
  PARTIAL: "A registry record matches, but nothing independent supports it. Public details can be copied, so a reviewer should look for more evidence.",
  UNVERIFIED: "No issuer record was found. This does NOT mean the letter is fake; the issuer may simply not have registered it here.",
  SUSPICIOUS: "Strong warning signs were found and there is no registry record to compare. A human reviewer should examine the evidence before any decision.",
  MISMATCH: "A registry record exists but this letter conflicts with it (or the approval is revoked). A reviewer should compare the differing fields.",
};

const G = (why, next) => ({ why, next });
export const FINDING_GUIDE = {
  missing_fields: G("Required details could not be read, so they cannot be checked against records.", "Upload a clearer copy or confirm the missing fields with the issuer."),
  low_ocr: G("The scan was hard to read, so extracted values may be wrong.", "Re-scan at higher quality; check extracted values manually."),
  no_text: G("No readable text was found.", "Upload the original PDF or a clearer image."),
  expired: G("The approval period in this letter has ended.", "Ask the institution for a current approval letter."),
  revoked: G("The issuer marked this record as revoked.", "Contact the issuer; do not rely on this letter."),
  ay_past: G("The academic year is in the past.", "Check whether a newer letter exists."),
  ref_format: G("The reference number does not follow the expected pattern. Formats can legitimately vary.", "Confirm the number with the issuer."),
  sig_broken: G("The file changed after it was signed, or the signature failed its integrity check.", "Request the original signed file from the issuer."),
  sig_untrusted: G("The signature is intact, but no trusted certificate authority is configured, so the signer's identity is NOT established.", "Treat as a weak positive only; confirm with the issuer."),
  sig_appended: G("Content was added after signing.", "Compare with the issuer's original."),
  wm_missing: G("The watermark the issuer registered was not found.", "Compare against a known original; scans can lose watermarks."),
  qr_offsite: G("The QR code points outside the configured official domains. It was decoded only, never opened.", "Do not scan or open it; confirm the link with the issuer."),
  qr_ref_mismatch: G("The QR code refers to a different reference number than the text.", "Compare both with the issuer's record."),
  edit_tool: G("File metadata shows an editing tool. Many legitimate workflows do this.", "Ask for the original export if other flags appear too."),
  exif_tool: G("The image was last saved by an editing tool.", "Ask for the original scan or photo."),
  mod_after_create: G("The file was modified after creation.", "Check whether later edits are expected."),
  incremental: G("The PDF contains incremental updates, so earlier versions may be embedded.", "Request a clean copy from the issuer."),
  ela: G("Error-level analysis found uneven compression. This heuristic is noisy and gives false positives.", "Use only alongside other evidence."),
  dup_file: G("This exact file was analysed before.", "Usually harmless; check whether the older result is still current."),
  dup_other: G("The identical file exists in other accounts. Shared letters are common.", "No action unless other flags appear."),
  ref_reuse: G("The reference number appears with a different institution elsewhere.", "Compare the documents and confirm with the issuer."),
  ref_ay_conflict: G("Another copy with this reference says a different academic year.", "Find out which version is current."),
  ref_valid_conflict: G("Another copy with this reference has a different validity date.", "Find out which version is current."),
};
export const guideFor = (id) => FINDING_GUIDE[id] || G("This rule flagged something worth a second look.", "Review the evidence and confirm with the issuer if unsure.");
