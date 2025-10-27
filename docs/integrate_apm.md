# OCI APM Integration

It is now possible to integrate the demo with **Oracle Cloud Infrastructure (OCI) Application Performance Monitoring (APM)** to automatically send *trace* and *span* data from your application to OCI APM.

---

## OpenTelemetry

This integration is based on the **OpenTelemetry Python** library, which provides vendor-neutral APIs and SDKs for distributed tracing and observability.

---

## Configuration

You can enable or disable APM integration using the `ENABLE_TRACING` flag in **`config.py`**.

In **`config_private.py`**, define your APM private data key:

```python
OCI_APM_DATA_KEY = "your-apm-data-key"
```

In **`config.py`**, set the following parameters:

```python
OTEL_SERVICE_NAME = "your-service-name"
OCI_APM_TRACES_URL = "your-apm-traces-url"
```

---

## Setup Steps

1. **Create an APM Domain**  
   In your OCI tenant, create a new **APM domain** if one does not already exist.

2. **Register Your Data Key and Domain URL**  
   - Obtain the **private data key** for your APM domain.  
   - Use the **trace ingestion URL** from the OCI console.  
   - Configure both values in your `config_private.py` and `config.py` as shown above.

---

## Notes

- Traces and spans are automatically collected and sent to OCI APM once tracing is enabled.  
- You can visualize traces in the OCI APM console under **Traces Explorer**.  
- Disabling `ENABLE_TRACING` will completely turn off trace collection without requiring code changes.


