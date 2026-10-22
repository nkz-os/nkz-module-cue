# CUE Anti-Corruption Layer
# NGSI-LD (JSON-LD) <-> SIEX XML (XSD)

# This package translates NGSI-LD entity graphs into SIEX-compliant
# XML payloads validated against FEGA XSD schemas (Anexo VI, v3.11.4).
#
# Supported payload types:
#   - Alta: new submission
#   - Modificacion: amendment (references original csv_trace_id)
#   - Anulacion: cancellation (references original csv_trace_id + motivo)
#
# NGSI-LD is a graph model (JSON-LD with Relationships).
# FEGA requires hierarchical XML with strict element names and nesting.
# This is NOT a 1:1 mapping -- the serializer resolves Relationships
# and flattens them into the XML hierarchy expected by SIEX.
